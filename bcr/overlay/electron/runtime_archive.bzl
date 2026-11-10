"""Build a Linux x64 runtime ZIP from declared upstream distribution files."""

def _impl(ctx):
    python = ctx.attr._python[platform_common.ToolchainInfo].py3_runtime
    if not python.interpreter:
        fail("Runtime assembly requires a declared Python interpreter")
    entries, inputs, seen = [], [], {}
    for group, prefix in [(ctx.attr.files, ""), (ctx.attr.libraries, "lib/")]:
        for target, path in group.items():
            if not path or path.startswith("/") or "\\" in path or ":" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
                fail("Runtime paths must be canonical and relative")
            destination = prefix + path
            if destination in seen:
                fail("Duplicate runtime destination: " + destination)
            files = target[DefaultInfo].files.to_list()
            if len(files) != 1 or files[0].is_directory:
                fail("Runtime inputs must identify exactly one regular file")
            seen[destination] = True
            inputs.append(files[0])
            entries.append({"source": files[0].path, "path": destination, "library": bool(prefix)})
    if any([path not in seen for path in ctx.attr.executables]):
        fail("Runtime executable is not a declared input")
    if any([path not in seen for path in ctx.attr.expected_sha256]):
        fail("Runtime hash guard lacks a declared input")
    modules = ctx.attr.nss_integrity_modules
    if len(modules) != len({name: True for name in modules}) or any([name not in ctx.attr.libraries.values() or not name.endswith(".so") for name in modules]):
        fail("NSS integrity modules must name distinct declared shared libraries")
    if (modules and not (ctx.executable.nss_integrity_tool and ctx.file.nss_parameters)) or (not modules and (ctx.executable.nss_integrity_tool or ctx.file.nss_parameters)):
        fail("NSS integrity requires modules, declared tool and upstream parameters")
    integrity = {}
    tools = [ctx.attr._patchelf[DefaultInfo].files_to_run]
    if modules:
        inputs += [ctx.file._nss_script, ctx.file.nss_parameters]
        tools.append(ctx.attr.nss_integrity_tool[DefaultInfo].files_to_run)
        integrity = {
            "modules": modules,
            "script": ctx.file._nss_script.path,
            "tool": ctx.executable.nss_integrity_tool.path,
            "parameters": ctx.file.nss_parameters.path,
        }
    manifest = ctx.actions.declare_file(ctx.label.name + ".inputs.json")
    ctx.actions.write(manifest, json.encode({
        "entries": entries,
        "executables": ctx.attr.executables,
        "host_abi": ctx.attr.host_abi,
        "expected_sha256": ctx.attr.expected_sha256,
        "patchelf": ctx.executable._patchelf.path,
        "archive": ctx.outputs.archive.path,
        "report": ctx.outputs.report.path,
        "nss_integrity": integrity,
    }))
    ctx.actions.run(
        executable = python.interpreter,
        arguments = ["-I", "-B", ctx.file._script.path, manifest.path],
        inputs = depset(inputs + [manifest, ctx.file._script], transitive = [python.files] if python.files else []),
        tools = tools,
        outputs = [ctx.outputs.archive, ctx.outputs.report],
        env = {"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronRuntimeArchive",
    )
    return [DefaultInfo(files = depset([ctx.outputs.archive, ctx.outputs.report]))]

electron_runtime_archive = rule(
    implementation = _impl,
    attrs = {
        "_python": attr.label(default = Label("//electron/private:execution_python"), cfg = "exec"),
        "files": attr.label_keyed_string_dict(allow_files = True, mandatory = True),
        "libraries": attr.label_keyed_string_dict(allow_files = True),
        "executables": attr.string_list(default = ["electron", "chrome-sandbox", "chrome_crashpad_handler"]),
        "host_abi": attr.string_list(doc = "Explicit host OS ABI SONAMEs; every other dependency must be bundled."),
        "expected_sha256": attr.string_dict(doc = "Optional distribution-path hashes for pinned notice inputs."),
        "nss_integrity_modules": attr.string_list(doc = "NSS shared libraries needing integrity metadata after ELF relocation."),
        "nss_integrity_tool": attr.label(executable = True, cfg = "exec"),
        "nss_parameters": attr.label(allow_single_file = True),
        "archive": attr.output(mandatory = True),
        "report": attr.output(mandatory = True),
        "_script": attr.label(default = Label("//electron/private:runtime_archive.py"), allow_single_file = True, cfg = "exec"),
        "_nss_script": attr.label(default = Label("//electron/private:nss_integrity.py"), allow_single_file = True, cfg = "exec"),
        "_patchelf": attr.label(default = Label("@patchelf//:patchelf"), executable = True, cfg = "exec"),
    },
)

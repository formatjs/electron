"""Declared upstream Python actions with matching execution-platform tools."""

def _impl(ctx):
    python = ctx.attr._python[platform_common.ToolchainInfo].py3_runtime
    if not python.interpreter:
        fail("Source generators require a declared Python interpreter")
    mappings = {}
    for target, logical in ctx.attr.srcs.items():
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("Each logical generator input must identify one file")
        mappings[logical] = files[0]
    source_groups = {target: "" for target in ctx.attr.source_groups}
    source_groups.update(ctx.attr.mapped_source_groups)
    for target, logical_root in source_groups.items():
        if logical_root and ("\\" in logical_root or ":" in logical_root or any([part in ["", ".", ".."] for part in logical_root.split("/")])):
            fail("Generator source-group prefix must be a canonical relative path")
        root = target.label.workspace_root
        prefix = root + "/" if root else ""
        for file in target[DefaultInfo].files.to_list():
            if not file.is_source or not file.path.startswith(prefix):
                fail("Generator source groups must contain repository source files")
            logical = (logical_root + "/" if logical_root else "") + file.path[len(prefix):]
            if logical in mappings and mappings[logical] != file:
                fail("Conflicting generator source-group path")
            mappings[logical] = file
    for logical, content in ctx.attr.literal_files.items():
        if not logical or logical.startswith("/") or "\\" in logical or ":" in logical or any([part in ["", ".", ".."] for part in logical.split("/")]):
            fail("Literal generator input must use a canonical relative path")
        if logical in mappings:
            fail("Literal generator input conflicts with a declared source")
        file = ctx.actions.declare_file(ctx.label.name + "_literal/" + logical)
        ctx.actions.write(file, content)
        mappings[logical] = file
    tools = []
    for target, logical in ctx.attr.tools.items():
        runner = target[DefaultInfo].files_to_run
        if logical in mappings:
            fail("Conflicting generator tool path")
        if runner and runner.executable:
            mappings[logical] = runner.executable
            tools.append(runner)
        else:
            files = target[DefaultInfo].files.to_list()
            if len(files) != 1:
                fail("Generator file tools must identify one pinned executable")
            mappings[logical] = files[0]
            tools.append(files[0])
    manifest = ctx.actions.declare_file(ctx.label.name + ".json")
    contents = {
        "inputs": [[file.path, logical] for logical, file in mappings.items()],
        "outputs": [[file.path, logical] for file, logical in zip(ctx.outputs.out_files, ctx.attr.logical_outputs)],
        "tools": ctx.attr.tools.values(),
        "script": ctx.attr.script,
        "args": ctx.attr.args,
        "response": ctx.attr.response,
        "environment": ctx.attr.environment,
        "verify_reproducible": ctx.attr.verify_reproducible,
    }
    if ctx.attr.python_tools:
        for script in ctx.attr.python_tools.values():
            if script not in mappings:
                fail("Python plugin scripts must be declared generator inputs")
        launcher = ctx.attr.python_launcher[DefaultInfo].files_to_run
        tools.append(launcher)
        contents["python_launcher"] = launcher.executable.path
        contents["python_tools"] = ctx.attr.python_tools
    ctx.actions.write(manifest, json.encode(contents))
    ctx.actions.run(
        executable = python.interpreter,
        arguments = ["-I", "-B", ctx.file._script.path, manifest.path],
        inputs = depset(mappings.values() + [manifest, ctx.file._script], transitive = ([python.files] if python.files else []) + [target[DefaultInfo].files for target in ctx.attr.deps] + [target[DefaultInfo].files for target in ctx.attr.tools] + [target[DefaultInfo].files for target in ctx.attr.tool_inputs]),
        tools = tools,
        outputs = ctx.outputs.out_files,
        env = {"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "PYTHONHASHSEED": "0"},
        mnemonic = "ElectronPython",
    )
    return [DefaultInfo(files = depset(ctx.outputs.out_files))]

_electron_source_action = rule(
    implementation = _impl,
    attrs = {
        "_python": attr.label(default = Label("//electron/private:execution_python"), cfg = "exec"),
        "srcs": attr.label_keyed_string_dict(allow_files = True),
        "literal_files": attr.string_dict(doc = "Declared logical input paths mapped to UTF-8 contents, including empty discovery markers."),
        "tools": attr.label_keyed_string_dict(cfg = "exec", allow_files = True),
        "source_groups": attr.label_list(cfg = "exec"),
        "mapped_source_groups": attr.label_keyed_string_dict(cfg = "exec"),
        "tool_inputs": attr.label_list(cfg = "exec"),
        "deps": attr.label_list(),
        "out_files": attr.output_list(mandatory = True),
        "logical_outputs": attr.string_list(mandatory = True),
        "script": attr.string(mandatory = True),
        "args": attr.string_list(),
        "response": attr.string_list(),
        "environment": attr.string_dict(),
        "python_tools": attr.string_dict(),
        "python_launcher": attr.label(executable = True, cfg = "exec"),
        "verify_reproducible": attr.bool(default = True),
        "_script": attr.label(default = Label("//electron/private:source_action.py"), allow_single_file = True, cfg = "exec"),
    },
)

def electron_source_action(name, python_tools = {}, **kwargs):
    """Run original generators with optional declared executable Python plugins."""
    _electron_source_action(
        name = name,
        python_tools = python_tools,
        python_launcher = Label("//electron/private:python_plugin_launcher") if python_tools else None,
        **kwargs
    )

"""Native generators with declared data beside their original executable."""

def _path(value):
    if value.startswith("/") or "\\" in value or any([part in ["", ".", ".."] for part in value.split("/")]):
        fail("Invalid native tool bundle path")
    return value

def _impl(ctx):
    runtime = ctx.toolchains["@rules_python//python:toolchain_type"].py3_runtime
    if not runtime.interpreter:
        fail("Native tool staging requires a declared Python interpreter")
    original = ctx.executable.binary
    binary = ctx.actions.declare_file(ctx.label.name + "_exec", sibling = original)
    ctx.actions.symlink(output = binary, target_file = original, is_executable = True)
    inputs, outputs = [], []
    copies = []
    seen = {original.basename: True, binary.basename: True}
    for target, relative in ctx.attr.data.items():
        relative = _path(relative)
        if relative in seen:
            fail("Duplicate native tool bundle output")
        seen[relative] = True
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("Native tool runtime inputs must identify one file")
        output = ctx.actions.declare_file(relative, sibling = original)
        inputs.append(files[0])
        outputs.append(output)
        copies.append([files[0].path, output.path])
    manifest = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.write(manifest, json.encode(copies))
    ctx.actions.run(
        executable = runtime.interpreter,
        arguments = ["-I", "-B", ctx.file._script.path, manifest.path],
        inputs = depset(inputs + [manifest, ctx.file._script], transitive = [runtime.files] if runtime.files else []),
        outputs = outputs,
        env = {"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronNativeToolBundle",
    )
    files = [binary, original] + outputs
    runfiles = ctx.runfiles(files = files).merge(ctx.attr.binary[DefaultInfo].default_runfiles)
    return [DefaultInfo(executable = binary, files = depset(files), runfiles = runfiles)]

electron_source_tool = rule(
    implementation = _impl,
    executable = True,
    toolchains = ["@rules_python//python:toolchain_type"],
    attrs = {
        "binary": attr.label(executable = True, cfg = "exec", mandatory = True),
        "data": attr.label_keyed_string_dict(allow_files = True, cfg = "exec"),
        "_script": attr.label(default = Label("//electron/private:source_tool.py"), allow_single_file = True),
    },
)

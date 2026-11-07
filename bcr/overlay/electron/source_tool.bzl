"""Declared standalone generators with data beside their executable."""

def _path(value):
    if value.startswith("/") or "\\" in value or any([part in ["", ".", ".."] for part in value.split("/")]):
        fail("Invalid native tool bundle path")
    return value

def _impl(ctx):
    runtime = ctx.toolchains["@rules_python//python:toolchain_type"].py3_runtime
    if not runtime.interpreter:
        fail("Native tool staging requires a declared Python interpreter")
    name = _path(ctx.attr.binary_name)
    if "/" in name:
        fail("Native tool executable must have one filename")
    binary = ctx.actions.declare_file(ctx.label.name + "/" + name)
    inputs, outputs = [ctx.executable.binary], [binary]
    copies = [[ctx.executable.binary.path, binary.path, True]]
    seen = {name: True}
    for target, relative in ctx.attr.data.items():
        relative = _path(relative)
        if relative in seen:
            fail("Duplicate native tool bundle output")
        seen[relative] = True
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("Native tool runtime inputs must identify one file")
        output = ctx.actions.declare_file(ctx.label.name + "/" + relative)
        inputs.append(files[0])
        outputs.append(output)
        copies.append([files[0].path, output.path, False])
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
    return [DefaultInfo(executable = binary, files = depset(outputs), runfiles = ctx.runfiles(files = outputs))]

electron_source_tool = rule(
    implementation = _impl,
    executable = True,
    toolchains = ["@rules_python//python:toolchain_type"],
    attrs = {
        "binary": attr.label(executable = True, cfg = "exec", mandatory = True),
        "binary_name": attr.string(mandatory = True),
        "data": attr.label_keyed_string_dict(allow_files = True, cfg = "exec"),
        "_script": attr.label(default = Label("//electron/private:source_tool.py"), allow_single_file = True),
    },
)

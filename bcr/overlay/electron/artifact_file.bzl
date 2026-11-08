"""Materialize declared artifact bytes under their runtime filename."""

def _impl(ctx):
    python = ctx.toolchains["@rules_python//python:toolchain_type"].py3_runtime
    if not python.interpreter:
        fail("Artifact staging requires a declared Python interpreter")
    ctx.actions.run(
        executable = python.interpreter,
        arguments = ["-I", "-B", ctx.file._script.path, ctx.file.src.path, ctx.outputs.out.path, "1" if ctx.attr.executable else "0"],
        inputs = depset([ctx.file.src, ctx.file._script], transitive = [python.files] if python.files else []),
        outputs = [ctx.outputs.out],
        env = {"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronArtifactFile",
    )
    return [DefaultInfo(files = depset([ctx.outputs.out]))]

electron_artifact_file = rule(
    implementation = _impl,
    toolchains = ["@rules_python//python:toolchain_type"],
    attrs = {
        "src": attr.label(allow_single_file = True, mandatory = True),
        "out": attr.output(mandatory = True),
        "executable": attr.bool(doc = "Normalize executable mode to 0755; data files use 0644."),
        "_script": attr.label(default = Label("//electron/private:artifact_file.py"), allow_single_file = True, cfg = "exec"),
    },
)

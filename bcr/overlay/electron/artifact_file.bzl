"""Materialize declared artifact bytes under their runtime filename."""

def _impl(ctx):
    ctx.actions.run(
        executable = ctx.attr._runner[DefaultInfo].files_to_run,
        arguments = [ctx.file.src.path, ctx.outputs.out.path],
        inputs = [ctx.file.src],
        outputs = [ctx.outputs.out],
        env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronArtifactFile",
    )
    return [DefaultInfo(files = depset([ctx.outputs.out]))]

electron_artifact_file = rule(
    implementation = _impl,
    attrs = {
        "src": attr.label(allow_single_file = True, mandatory = True),
        "out": attr.output(mandatory = True),
        "_runner": attr.label(default = Label("//electron/private:artifact_file"), executable = True, cfg = "exec"),
    },
)

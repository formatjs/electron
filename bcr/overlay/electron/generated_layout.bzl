"""Expose already-verified generator outputs at their captured logical paths."""

def _impl(ctx):
    available = {}
    prefix = "/" + ctx.attr.src.label.package + "/" + ctx.attr.src.label.name + "/"
    for file in ctx.attr.src[DefaultInfo].files.to_list():
        before, marker, relative = file.path.rpartition(prefix)
        if marker:
            if relative in available:
                fail("Duplicate original generated input")
            available[relative] = file
    if len(ctx.outputs.out_files) != len(ctx.attr.relative_inputs):
        fail("Generated layout output arity differs")
    for output, relative in zip(ctx.outputs.out_files, ctx.attr.relative_inputs):
        if relative not in available:
            fail("Missing original generated input: " + relative)
        ctx.actions.symlink(output = output, target_file = available[relative])
    return [DefaultInfo(files = depset(ctx.outputs.out_files))]

electron_generated_layout = rule(
    implementation = _impl,
    attrs = {
        "src": attr.label(mandatory = True),
        "out_files": attr.output_list(mandatory = True),
        "relative_inputs": attr.string_list(mandatory = True),
    },
)

"""Project exact PartitionAlloc sources from the pinned, patched Chromium tree."""

def _impl(ctx):
    ctx.read(ctx.attr.chromium)
    root = ctx.path(ctx.attr.chromium).dirname.get_child("base/allocator/partition_allocator")
    for entry in root.readdir():
        if entry.basename not in ["BUILD", "BUILD.bazel"]:
            ctx.symlink(entry, entry.basename)
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_partition_alloc_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "build_file": attr.label(default = Label("//source:partition_alloc.BUILD.bazel")),
    },
)

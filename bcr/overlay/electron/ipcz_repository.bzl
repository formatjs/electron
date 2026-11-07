"""Project the matching original Chromium IPCz source tree read-only."""

def _impl(ctx):
    ctx.read(ctx.attr.chromium)
    root = ctx.path(ctx.attr.chromium).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if not path.startswith("third_party/ipcz/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid IPCz source path")
        ctx.symlink(root.get_child(path), path)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_ipcz_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:ipcz_inputs.json")),
        "build_file": attr.label(default = Label("//source:ipcz.BUILD.bazel")),
    },
)

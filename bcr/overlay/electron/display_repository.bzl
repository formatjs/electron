"""Read-only native display source projection and original GN metadata."""

def _impl(ctx):
    ctx.read(ctx.attr.chromium)
    root = ctx.path(ctx.attr.chromium).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid native display source path")
        ctx.symlink(root.get_child(path), path)
    for path, content in profile["generated_files"].items():
        if not path.startswith("//out/bazel-import/") or ".." in path.split("/"):
            fail("Invalid native display metadata path")
        ctx.file(path[2:], content, executable = False)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_display_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:display_inputs.json")),
        "build_file": attr.label(default = Label("//source:display.BUILD.bazel")),
    },
)

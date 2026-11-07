"""Read-only typed Mojo source projection and original GN metadata."""

def _impl(ctx):
    ctx.read(ctx.attr.chromium)
    root = ctx.path(ctx.attr.chromium).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid typed Mojo source path")
        if path == "mojo/public/tools/mojom/mojom_parser.py":
            ctx.file(path, ctx.read(root.get_child(path)), executable = False)
        else:
            ctx.symlink(root.get_child(path), path)
    ctx.patch(ctx.attr.metadata_patch, strip = 1)
    ctx.file("native_compat_patches.json", json.encode({"graph_sha256": profile["graph_sha256"], "patches": [str(ctx.attr.metadata_patch)], "files": ["mojo/public/tools/mojom/mojom_parser.py"]}))
    for path, content in profile["generated_files"].items():
        if not path.startswith("//out/bazel-import/") or ".." in path.split("/"):
            fail("Invalid typed Mojo metadata path")
        ctx.file(path[2:], content, executable = False)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_mojo_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "metadata_patch": attr.label(default = Label("//source:mojo_relative_metadata.patch")),
        "profile": attr.label(default = Label("//source/native:mojo_inputs.json")),
        "build_file": attr.label(default = Label("//source:mojo.BUILD.bazel")),
    },
)

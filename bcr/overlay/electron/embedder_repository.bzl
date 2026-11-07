"""Project matching Gin/i18n sources and exact CED inputs read-only."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "ced": ctx.attr.ced}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid embedder source path")
        owner = "ced" if path.startswith("third_party/ced/src/") else "chromium"
        relative = path[len("third_party/ced/src/"):] if owner == "ced" else path
        ctx.symlink(roots[owner].get_child(relative), path)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_embedder_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "ced": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:embedder_inputs.json")),
        "build_file": attr.label(default = Label("//source:embedder.BUILD.bazel")),
    },
)

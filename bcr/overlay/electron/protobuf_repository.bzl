"""Project matching Protobuf and its declared JavaScript compiler plugin."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "javascript": ctx.attr.javascript}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid Protobuf source path")
        prefix = "third_party/protobuf-javascript/src/"
        origin = roots["javascript"].get_child(path[len(prefix):]) if path.startswith(prefix) else roots["chromium"].get_child(path)
        ctx.symlink(origin, path)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_protobuf_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "javascript": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:protobuf_inputs.json")),
        "build_file": attr.label(default = Label("//source:protobuf.BUILD.bazel")),
    },
)

"""Read-only projection of matching Mojo/network sources and captured GN files."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "quiche": ctx.attr.quiche, "re2": ctx.attr.re2, "sqlite": ctx.attr.sqlite}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid network source path")
        owner, relative = "chromium", path
        for prefix, name in {"net/third_party/quiche/src/": "quiche", "third_party/re2/src/": "re2", "third_party/sqlite/src/": "sqlite"}.items():
            if path.startswith(prefix):
                owner, relative = name, path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    for path, content in profile["generated_files"].items():
        if not path.startswith("//out/bazel-import/") or ".." in path.split("/"):
            fail("Invalid captured network file path")
        ctx.file(path[2:], content, executable = False)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_network_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "quiche": attr.label(mandatory = True),
        "re2": attr.label(mandatory = True),
        "sqlite": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:network_inputs.json")),
        "build_file": attr.label(default = Label("//source:network.BUILD.bazel")),
    },
)

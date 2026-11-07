"""Read-only projection of the exact V8 support dependency inputs."""

def _impl(ctx):
    anchors = {"chromium": ctx.attr.chromium, "dragonbox": ctx.attr.dragonbox, "fast_float": ctx.attr.fast_float, "highway": ctx.attr.highway}
    roots = {}
    for name, anchor in anchors.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid V8 support source path")
        owner = "chromium"
        relative = path
        for name in ["dragonbox", "fast_float", "highway"]:
            prefix = profile["roots"][name] + "/"
            if path.startswith(prefix):
                owner = name
                relative = path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_v8_support_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "dragonbox": attr.label(mandatory = True),
        "fast_float": attr.label(mandatory = True),
        "highway": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:v8_support_inputs.json")),
        "build_file": attr.label(default = Label("//source:v8_support.BUILD.bazel")),
    },
)

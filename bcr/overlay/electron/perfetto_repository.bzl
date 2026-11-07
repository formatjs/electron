"""Read-only projection of patched Perfetto, matching JsonCpp and generator inputs."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "perfetto": ctx.attr.perfetto, "jsoncpp": ctx.attr.jsoncpp}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid Perfetto source path")
        owner = "chromium"
        relative = path
        for name, prefix in {"perfetto": "third_party/perfetto/", "jsoncpp": "third_party/jsoncpp/source/"}.items():
            if path.startswith(prefix):
                owner = name
                relative = path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_perfetto_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "perfetto": attr.label(mandatory = True),
        "jsoncpp": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:perfetto_inputs.json")),
        "build_file": attr.label(default = Label("//source:perfetto.BUILD.bazel")),
    },
)

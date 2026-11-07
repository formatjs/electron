"""Project declared Chromium base sources without modifying upstream trees."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "electron": ctx.attr.electron, "lss": ctx.attr.lss}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid Chromium base source path")
        owner = "chromium"
        relative = path
        for name, prefix in {"electron": "electron/", "lss": "third_party/lss/"}.items():
            if path.startswith(prefix):
                owner = name
                relative = path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_base_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "electron": attr.label(default = Label("//:DEPS")),
        "lss": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:base_inputs.json")),
        "build_file": attr.label(default = Label("//source:base.BUILD.bazel")),
    },
)

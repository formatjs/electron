"""Read-only matching graphics sources and original GN metadata."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "libdrm": ctx.attr.libdrm, "libsync": ctx.attr.libsync}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid graphics source path")
        owner, relative = "chromium", path
        for prefix, name in {"third_party/libdrm/src/": "libdrm", "third_party/libsync/src/": "libsync"}.items():
            if path.startswith(prefix):
                owner, relative = name, path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    for path, content in profile["generated_files"].items():
        if not path.startswith("//out/bazel-import/") or ".." in path.split("/"):
            fail("Invalid graphics metadata path")
        ctx.file(path[2:], content, executable = False)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_gfx_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "libdrm": attr.label(mandatory = True),
        "libsync": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:gfx_inputs.json")),
        "build_file": attr.label(default = Label("//source:gfx.BUILD.bazel")),
    },
)

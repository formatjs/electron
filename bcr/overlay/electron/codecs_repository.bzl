"""Read-only matching codec/NASM source projection."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "jpeg": ctx.attr.jpeg, "webp": ctx.attr.webp, "wuffs": ctx.attr.wuffs, "nasm": ctx.attr.nasm}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid codec/NASM source path")
        owner, relative = "chromium", path
        for prefix, name in {"third_party/libjpeg_turbo/": "jpeg", "third_party/libwebp/src/": "webp", "third_party/wuffs/src/": "wuffs", "third_party/nasm/": "nasm"}.items():
            if path.startswith(prefix):
                owner, relative = name, path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_codecs_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "jpeg": attr.label(mandatory = True),
        "webp": attr.label(mandatory = True),
        "wuffs": attr.label(mandatory = True),
        "nasm": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:codecs_inputs.json")),
        "build_file": attr.label(default = Label("//source:codecs.BUILD.bazel")),
    },
)

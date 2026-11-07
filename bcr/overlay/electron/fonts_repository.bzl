"""Read-only matching font/XML sources, retaining Chromium's custom configuration."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "freetype": ctx.attr.freetype, "harfbuzz": ctx.attr.harfbuzz}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid font/XML source path")
        owner, relative = "chromium", path
        for prefix, name in {"third_party/freetype/src/": "freetype", "third_party/harfbuzz-ng/src/": "harfbuzz"}.items():
            if path.startswith(prefix):
                owner, relative = name, path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_fonts_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "freetype": attr.label(mandatory = True),
        "harfbuzz": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:fonts_inputs.json")),
        "build_file": attr.label(default = Label("//source:fonts.BUILD.bazel")),
    },
)

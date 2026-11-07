"""Read-only matching Skia/Dawn sources and original GN metadata."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "skia": ctx.attr.skia, "dawn": ctx.attr.dawn, "vulkan": ctx.attr.vulkan}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid Skia source path")
        owner, relative = "chromium", path
        for prefix, name in {"third_party/skia/": "skia", "third_party/dawn/": "dawn", "third_party/vulkan-headers/src/": "vulkan"}.items():
            if path.startswith(prefix):
                owner, relative = name, path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    for path, content in profile["source_metadata"].items():
        if path != "gpu/webgpu/DAWN_VERSION":
            fail("Unexpected Skia source metadata")
        ctx.file(path, content, executable = False)
    for path, content in profile["generated_files"].items():
        if not path.startswith("//out/bazel-import/") or ".." in path.split("/"):
            fail("Invalid Skia metadata path")
        ctx.file(path[2:], content, executable = False)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_skia_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "skia": attr.label(mandatory = True),
        "dawn": attr.label(mandatory = True),
        "vulkan": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:skia_inputs.json")),
        "build_file": attr.label(default = Label("//source:skia.BUILD.bazel")),
    },
)

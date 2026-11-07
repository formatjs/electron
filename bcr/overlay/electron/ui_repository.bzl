"""Read-only matching UI/WebUI sources and original GN metadata."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "node_modules": ctx.attr.node_modules}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname.get_child("node_modules") if name == "node_modules" else ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid UI source path")
        owner, relative = "chromium", path
        for prefix, name in {"third_party/node/node_modules/": "node_modules"}.items():
            if path.startswith(prefix):
                owner, relative = name, path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    for path, content in profile["generated_files"].items():
        if not path.startswith("//out/bazel-import/") or ".." in path.split("/"):
            fail("Invalid UI metadata path")
        ctx.file(path[2:], content, executable = False)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_ui_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "node_modules": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:ui_inputs.json")),
        "build_file": attr.label(default = Label("//source:ui.BUILD.bazel")),
    },
)

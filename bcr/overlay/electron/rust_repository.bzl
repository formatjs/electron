"""Project declared Electron Rust inputs from pinned source archives."""

def _impl(ctx):
    ctx.read(ctx.attr.chromium)
    root = ctx.path(ctx.attr.chromium).dirname
    ctx.read(ctx.attr.fontconfig)
    fontconfig = ctx.path(ctx.attr.fontconfig).dirname
    ctx.read(ctx.attr.skia)
    skia = ctx.path(ctx.attr.skia).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    files = {path: True for path in profile["root_files"]}
    for paths in profile["packages"].values():
        files.update({path: True for path in paths})
    for path in sorted(files):
        if path.startswith("/") or any([part in ["", ".", ".."] for part in path.split("/")]) or "\\" in path:
            fail("Invalid projected Rust source path")
        prefix = "third_party/fontconfig/src/"
        origin = fontconfig.get_child(path[len(prefix):]) if path.startswith(prefix) else root.get_child(path)
        if path.startswith("third_party/skia/"):
            origin = skia.get_child(path[len("third_party/skia/"):])
        ctx.symlink(origin, path)
    for package, paths in profile["packages"].items():
        relative = [path[len(package) + 1:] for path in paths]
        ctx.file(package + "/BUILD.bazel", "package(default_visibility = [\"//visibility:public\"])\nexports_files(" + json.encode(relative) + ")\nfilegroup(name = \"files\", srcs = " + json.encode(relative) + ")\n")
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_rust_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "fontconfig": attr.label(mandatory = True),
        "skia": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:temporal_inputs.json")),
        "build_file": attr.label(default = Label("//source:rust.BUILD.bazel")),
    },
)

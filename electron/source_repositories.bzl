"""Electron's patched native source trees, independent of runtime downloads."""

def _electron_sources_impl(ctx):
    ctx.download_and_extract(
        url = "https://github.com/electron/electron/archive/refs/tags/v39.0.0.tar.gz",
        sha256 = "99ea4a5a0b2c1a8182f478cf603209a996007ea402934cb20132fae6475604d9",
        stripPrefix = "electron-39.0.0",
    )
    ctx.file("BUILD.bazel", """package(default_visibility = ["//visibility:public"])
exports_files(["DEPS", "BUILD.gn", "LICENSE"])
filegroup(name = "patches", srcs = glob(["patches/**"], exclude = ["patches/**/.git/**"], exclude_directories = 1))
filegroup(name = "shell", srcs = glob(["shell/**"]))
filegroup(name = "sources", srcs = glob(["**"], exclude = ["BUILD.bazel"]))
""")

electron_sources_repository = repository_rule(implementation = _electron_sources_impl)

def _node_sources_impl(ctx):
    ctx.download_and_extract(
        url = "https://github.com/nodejs/node/archive/refs/tags/v22.20.0.tar.gz",
        sha256 = "5c2e4ecc6583c5d49f9a9a4473fc267402762fc8e8a7835465919dacd6fdd5d8",
        stripPrefix = "node-22.20.0",
    )
    electron_root = ctx.path(ctx.attr.electron).dirname
    stack = electron_root.get_child("patches/node")
    patches = [line.strip() for line in ctx.read(stack.get_child(".patches")).splitlines() if line.strip()]
    for patch in patches:
        ctx.patch(stack.get_child(patch), strip = 1)
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))
    ctx.file("electron_patches.json", json.encode(patches))
    ctx.file("uv_sources.bzl", ctx.read(ctx.attr.uv_sources))

electron_node_repository = repository_rule(
    implementation = _node_sources_impl,
    attrs = {"electron": attr.label(mandatory = True), "build_file": attr.label(default = Label("//source:node.BUILD.bazel")), "uv_sources": attr.label(default = Label("//source:uv_sources.bzl"))},
)

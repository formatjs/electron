"""Electron's patched native source trees, independent of runtime downloads."""

load(":archive_urls.bzl", "source_archive_urls")

def _node_sources_impl(ctx):
    ctx.download_and_extract(
        url = source_archive_urls("https://github.com/nodejs/node/archive/refs/tags/v22.20.0.tar.gz"),
        type = "tar.gz",
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
    ctx.file("deps/v8/tools/BUILD.bazel", "exports_files(glob([\"*.mjs\"]))\n")

electron_node_repository = repository_rule(
    implementation = _node_sources_impl,
    attrs = {"electron": attr.label(mandatory = True), "build_file": attr.label(default = Label("//source:node.BUILD.bazel")), "uv_sources": attr.label(default = Label("//source:uv_sources.bzl"))},
)

def _embedded_abseil_impl(ctx):
    ctx.read(ctx.attr.chromium)
    root = ctx.path(ctx.attr.chromium).dirname.get_child("third_party/abseil-cpp")
    for entry in root.readdir():
        ctx.symlink(entry, entry.basename)

electron_abseil_repository = repository_rule(
    implementation = _embedded_abseil_impl,
    attrs = {"chromium": attr.label(mandatory = True)},
)

def _patched_upstream_impl(ctx):
    ctx.download_and_extract(url = source_archive_urls(ctx.attr.url), sha256 = ctx.attr.sha256, stripPrefix = ctx.attr.strip_prefix, type = "tar.gz" if ctx.attr.url.endswith(".tar.gz") else "")
    stack = ctx.path(ctx.attr.electron).dirname.get_child("patches/" + ctx.attr.patch_group)
    patches = [line.strip() for line in ctx.read(stack.get_child(".patches")).splitlines() if line.strip()]
    for patch in patches:
        ctx.patch(stack.get_child(patch), strip = 1)
    ctx.file("electron_patches.json", json.encode({"electron_version": "39.0.0", "upstream_revision": ctx.attr.revision, "upstream_sha256": ctx.attr.sha256, "patch_group": ctx.attr.patch_group, "patches": patches}))
    ctx.file("BUILD.bazel", """package(default_visibility = ["//visibility:public"])
exports_files(["electron_patches.json", "DEPS"])
filegroup(name = "sources", srcs = glob(["**"], exclude = ["BUILD.bazel"]))
""")
    if ctx.attr.patch_group == "chromium":
        ctx.file("BUILD.bazel", """load("@rules_cc//cc:cc_library.bzl", "cc_library")
package(default_visibility = ["//visibility:public"])
exports_files(["electron_patches.json", "DEPS", "build/write_buildflag_header.py"])
filegroup(name = "sources", srcs = glob(["**"], exclude = ["BUILD.bazel"]))
cc_library(name = "fuse_base_headers", hdrs = ["base/dcheck_is_on.h", "build/buildflag.h"], includes = ["."])
""")
    elif ctx.attr.patch_group == "v8":
        ctx.file("BUILD.bazel", ctx.read(ctx.attr.v8_build_file))
        ctx.file("testing/gtest/include/gtest/gtest_prod.h", '#include "gtest/gtest_prod.h"\n')

electron_patched_upstream = repository_rule(
    implementation = _patched_upstream_impl,
    attrs = {
        "electron": attr.label(mandatory = True),
        "patch_group": attr.string(mandatory = True),
        "url": attr.string(mandatory = True),
        "sha256": attr.string(mandatory = True),
        "strip_prefix": attr.string(mandatory = True),
        "revision": attr.string(mandatory = True),
        "v8_build_file": attr.label(default = Label("//source:v8.BUILD.bazel")),
    },
)

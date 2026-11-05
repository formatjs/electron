"""Pinned official Electron distributions; downloads happen during repository resolution."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "new_git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive", "http_file")
load(":source_repositories.bzl", "electron_node_repository", "electron_patched_upstream", "electron_sources_repository")

_VERSION = "39.0.0"
_SHA256 = {
    "darwin_arm64": "678e51190e5b29af4eb5842d4724db35409efb706ce17b1a40faf823720a9c70",
    "linux_arm64": "8985a9b2055c17f2bdae4418af140d6accd12b28f929319f5a918ca79b0a3d43",
    "linux_amd64": "4520cbd92eeed370d7cfd2b1c60135647c02b8f634d6179d8a9a3f64b64baf2f",
    "windows_arm64": "31fe7805a77c2c6accfede1c954fc4a3f43816e7c921a11cf8f34f57da7f40dc",
    "windows_amd64": "bdcf82b95100a4b770dded1587d8d9dafddf782079127a8dbdc1891faef324a5",
}
_UPSTREAM = {"darwin_arm64": "darwin-arm64", "linux_arm64": "linux-arm64", "linux_amd64": "linux-x64", "windows_arm64": "win32-arm64", "windows_amd64": "win32-x64"}

def _hub_impl(ctx):
    lines = ["load(\"@rules_electron//electron:defs.bzl\", \"electron_runtime\")", "package(default_visibility = [\"//visibility:public\"])"]
    for platform in sorted(_SHA256):
        lines.append("electron_runtime(name = %r, archive = %r, platform = %r, version = %r)" % (platform, "@electron_" + platform + "//file", platform, _VERSION))
    lines.append("alias(name = \"runtime\", actual = select({")
    for platform in sorted(_SHA256):
        lines.append("    \"@rules_electron//platforms:is_%s\": \":%s\"," % (platform, platform))
    lines.append("}, no_match_error = \"Unsupported Electron target platform\"))")
    ctx.file("BUILD.bazel", "\n".join(lines))

_hub = repository_rule(implementation = _hub_impl)

def _impl(ctx):
    versions = {tag.version: True for module in ctx.modules for tag in module.tags.version}
    if versions.keys() != [_VERSION]:
        fail("Supported Electron version: " + _VERSION + "; pin new versions and their checked-in SHA256 digests first")
    for platform, checksum in _SHA256.items():
        filename = "electron-v%s-%s.zip" % (_VERSION, _UPSTREAM[platform])
        http_file(name = "electron_" + platform, urls = ["https://github.com/electron/electron/releases/download/v%s/%s" % (_VERSION, filename)], sha256 = checksum, downloaded_file_path = filename)
    electron_patched_upstream(
        name = "electron_chromium_sources",
        electron = "@electron_sources//:DEPS",
        patch_group = "chromium",
        url = "https://github.com/chromium/chromium/archive/refs/tags/142.0.7444.52.tar.gz",
        sha256 = "dbc3dc2d84dde007c0afb307e0ce1d008a126f57afb69ff6d44744b874714302",
        strip_prefix = "chromium-142.0.7444.52",
        revision = "7efca501bfcc84657ba2921a852e98ce1fb37641",
    )
    electron_patched_upstream(
        name = "electron_v8_sources",
        electron = "@electron_sources//:DEPS",
        patch_group = "v8",
        url = "https://github.com/v8/v8/archive/bb294624702efbb17691b642333f06bf5108e600.tar.gz",
        sha256 = "6923eecf791b219cab0d72527b8e6a1c61c64f81a085d16b0eee96ca1ef8976c",
        strip_prefix = "v8-bb294624702efbb17691b642333f06bf5108e600",
        revision = "bb294624702efbb17691b642333f06bf5108e600",
    )
    new_git_repository(
        name = "electron_cast_core_sources",
        remote = "https://chromium.googlesource.com/cast_core/public",
        commit = "f5ee589bdaea60418f670fa176be15ccb9a34942",
        build_file_content = "exports_files([\"proto/proto.gni\"], visibility = [\"//visibility:public\"])",
    )
    http_archive(
        name = "electron_glslang_sources",
        urls = ["https://github.com/KhronosGroup/glslang/archive/a57276bf558f5cf94d3a9854ebdf5a2236849a5a.tar.gz"],
        sha256 = "02f4321a3ed01b9a9a9874f76e2d8ad078825818fcc9aae12dbf2c01674fb8af",
        strip_prefix = "glslang-a57276bf558f5cf94d3a9854ebdf5a2236849a5a",
        build_file_content = "exports_files([\"BUILD.gn\"], visibility = [\"//visibility:public\"])",
    )
    _hub(name = "electron_runtime")
    electron_sources_repository(name = "electron_sources")
    electron_node_repository(name = "electron_node_sources", electron = "@electron_sources//:DEPS")
    direct = ["electron_runtime"]
    if any([tag.sources for module in ctx.modules if module.is_root for tag in module.tags.version]):
        direct += ["electron_sources", "electron_node_sources", "electron_v8_sources", "electron_chromium_sources", "electron_cast_core_sources", "electron_glslang_sources"]
    return ctx.extension_metadata(reproducible = True, root_module_direct_deps = direct, root_module_direct_dev_deps = [])

electron = module_extension(implementation = _impl, tag_classes = {"version": tag_class(attrs = {"version": attr.string(mandatory = True), "sources": attr.bool(default = False)})})

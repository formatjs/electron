"""Pinned official Electron distributions; downloads happen during repository resolution."""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_file")
load(":source_repositories.bzl", "electron_node_repository", "electron_sources_repository")

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
    _hub(name = "electron_runtime")
    electron_sources_repository(name = "electron_sources")
    electron_node_repository(name = "electron_node_sources", electron = "@electron_sources//:DEPS")
    direct = ["electron_runtime"]
    if any([tag.sources for module in ctx.modules if module.is_root for tag in module.tags.version]):
        direct += ["electron_sources", "electron_node_sources"]
    return ctx.extension_metadata(reproducible = True, root_module_direct_deps = direct, root_module_direct_dev_deps = [])

electron = module_extension(implementation = _impl, tag_classes = {"version": tag_class(attrs = {"version": attr.string(mandatory = True), "sources": attr.bool(default = False)})})

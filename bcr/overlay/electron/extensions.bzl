"""Exact, patched dependencies for the Electron source overlay."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository", "new_git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load(":source_repositories.bzl", "electron_abseil_repository", "electron_icu_repository", "electron_node_repository", "electron_patched_upstream")

_VERSION = "39.0.0"

def _impl(ctx):
    versions = {tag.version: True for module in ctx.modules for tag in module.tags.version}
    if versions.keys() != [_VERSION]:
        fail("Supported Electron version: " + _VERSION + "; pin new versions and their checked-in SHA256 digests first")
    electron_patched_upstream(
        name = "electron_chromium_sources",
        electron = "@electron//:DEPS",
        patch_group = "chromium",
        url = "https://github.com/chromium/chromium/archive/refs/tags/142.0.7444.52.tar.gz",
        sha256 = "dbc3dc2d84dde007c0afb307e0ce1d008a126f57afb69ff6d44744b874714302",
        strip_prefix = "chromium-142.0.7444.52",
        revision = "7efca501bfcc84657ba2921a852e98ce1fb37641",
    )
    electron_patched_upstream(
        name = "electron_v8_sources",
        electron = "@electron//:DEPS",
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
    dependency_repos = []
    for entry in json.decode(ctx.read(Label("//source:upstream_pins.json"))):
        group = entry["group"]
        if group in ["chromium", "node", "v8"]:
            continue
        name = "electron_" + group.lower().replace(".", "_").replace("-", "_") + "_sources"
        remote, commit = entry["url"].rsplit("@", 1)
        patches = ["@electron//:patches/%s/%s" % (group, patch) for patch in entry["patches"]]
        if group == "boringssl":
            git_repository(name = name, remote = remote, commit = commit, patches = patches + [Label("//source:boringssl-electron.patch")], patch_strip = 1)
        else:
            new_git_repository(name = name, remote = remote, commit = commit, patches = patches, patch_strip = 1, build_file_content = "package(default_visibility = [\"//visibility:public\"])\nfilegroup(name = \"source_anchor\", srcs = glob([\"*\"], exclude = [\"BUILD.bazel\"]))")
        dependency_repos.append(name)
    electron_abseil_repository(name = "electron_abseil_sources", chromium = "@electron_chromium_sources//:DEPS")
    electron_icu_repository(name = "electron_icu_sources", chromium = "@electron_chromium_sources//:DEPS")
    electron_node_repository(name = "electron_node_sources", electron = "@electron//:DEPS")
    direct = ["electron_node_sources", "electron_v8_sources", "electron_chromium_sources", "electron_cast_core_sources", "electron_glslang_sources", "electron_abseil_sources", "electron_icu_sources"] + dependency_repos
    return ctx.extension_metadata(reproducible = True, root_module_direct_deps = direct, root_module_direct_dev_deps = [])

electron = module_extension(implementation = _impl, tag_classes = {"version": tag_class(attrs = {"version": attr.string(mandatory = True)})})

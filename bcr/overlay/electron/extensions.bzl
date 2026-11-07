"""Exact, patched dependencies for the Electron source overlay."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository", "new_git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load(":base_repository.bzl", "electron_base_repository")
load(":icu_repository.bzl", "electron_icu_repository")
load(":libnode_repository.bzl", "electron_libnode_repository")
load(":partition_alloc_repository.bzl", "electron_partition_alloc_repository")
load(":perfetto_repository.bzl", "electron_perfetto_repository")
load(":protobuf_repository.bzl", "electron_protobuf_repository")
load(":rust_repository.bzl", "electron_rust_repository")
load(":source_repositories.bzl", "electron_abseil_repository", "electron_node_repository", "electron_patched_upstream")
load(":v8_engine_repository.bzl", "electron_v8_engine_repository")
load(":v8_support_repository.bzl", "electron_v8_support_repository")

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
            new_git_repository(name = name, remote = remote, commit = commit, patches = patches, patch_strip = 1, build_file_content = "package(default_visibility = [\"//visibility:public\"])\n" + ("exports_files([\"BUILD.gn\"])\n" if group == "perfetto" else "") + "filegroup(name = \"source_anchor\", srcs = glob([\"*\"], exclude = [\"BUILD.bazel\"]))")
        dependency_repos.append(name)
    electron_abseil_repository(name = "electron_abseil_sources", chromium = "@electron_chromium_sources//:DEPS")
    electron_icu_repository(name = "electron_icu_sources", chromium = "@electron_chromium_sources//:DEPS")
    electron_partition_alloc_repository(name = "electron_partition_alloc_sources", chromium = "@electron_chromium_sources//:DEPS")
    electron_rust_repository(name = "electron_rust_sources", chromium = "@electron_chromium_sources//:DEPS")
    http_archive(
        name = "electron_lss_upstream",
        urls = ["https://github.com/citizenfx/linux-syscall-support/archive/ed31caa60f20a4f6569883b2d752ef7522de51e0.tar.gz"],
        integrity = "sha256-KE6rt4Lt3wvLrjNSL/lxwepRYUlWqA500k4od6o9oAA=",
        strip_prefix = "linux-syscall-support-ed31caa60f20a4f6569883b2d752ef7522de51e0",
        build_file_content = "exports_files([\"LICENSE\"], visibility = [\"//visibility:public\"])\n",
    )
    electron_base_repository(name = "electron_base_sources", chromium = "@electron_chromium_sources//:DEPS", lss = "@electron_lss_upstream//:LICENSE")
    http_archive(
        name = "electron_zstd_upstream",
        urls = ["https://github.com/facebook/zstd/archive/89d685e42dbcf815a16ed0fcd7d050ef74ccad96.tar.gz"],
        sha256 = "76ee6726cb6971b7c14274cb5ae6a41ea03adedbdf829bc96449cdffe93aa913",
        strip_prefix = "zstd-89d685e42dbcf815a16ed0fcd7d050ef74ccad96",
        build_file_content = "exports_files([\"LICENSE\"], visibility = [\"//visibility:public\"])\n",
    )
    electron_libnode_repository(
        name = "electron_libnode_sources",
        chromium = "@electron_chromium_sources//:DEPS",
        node = "@electron_node_sources//:LICENSE",
        v8 = "@electron_v8_sources//:DEPS",
        zstd = "@electron_zstd_upstream//:LICENSE",
    )
    http_archive(
        name = "electron_fp16_upstream",
        urls = ["https://github.com/Maratyszcza/FP16/archive/3d2de1816307bac63c16a297e8c4dc501b4076df.tar.gz"],
        sha256 = "65ace2f05fd9434b0acb7a7d3cc6cd96842ea6236b680594af932b359bedbfc1",
        strip_prefix = "FP16-3d2de1816307bac63c16a297e8c4dc501b4076df",
        build_file_content = "exports_files([\"BUILD.bazel\"], visibility = [\"//visibility:public\"])\n",
    )
    electron_v8_engine_repository(
        name = "electron_v8_engine_sources",
        v8 = "@electron_v8_sources//:DEPS",
        chromium = "@electron_chromium_sources//:DEPS",
        fp16 = "@electron_fp16_upstream//:BUILD.bazel",
    )
    http_archive(
        name = "electron_jsoncpp_upstream",
        urls = ["https://github.com/open-source-parsers/jsoncpp/archive/42e892d96e47b1f6e29844cc705e148ec4856448.tar.gz"],
        sha256 = "0b40e4598d68d3dbd8cab90b249e18f1363ecc694c38f727851f4db34b6887ec",
        strip_prefix = "jsoncpp-42e892d96e47b1f6e29844cc705e148ec4856448",
        build_file_content = "exports_files([\"BUILD.bazel\"], visibility = [\"//visibility:public\"])\n",
    )
    electron_perfetto_repository(
        name = "electron_perfetto_native_sources",
        chromium = "@electron_chromium_sources//:DEPS",
        perfetto = "@electron_perfetto_sources//:BUILD.gn",
        jsoncpp = "@electron_jsoncpp_upstream//:BUILD.bazel",
    )
    http_archive(
        name = "electron_protobuf_javascript_upstream",
        urls = ["https://github.com/protocolbuffers/protobuf-javascript/archive/e6d763860001ba1a76a63adcff5efb12b1c96024.tar.gz"],
        sha256 = "dd78fad1311e7819913047f5ee544a384183ae88ca118a22f6d4992d4b2a081b",
        strip_prefix = "protobuf-javascript-e6d763860001ba1a76a63adcff5efb12b1c96024",
        build_file_content = "exports_files([\"BUILD.bazel\"], visibility = [\"//visibility:public\"])\n",
    )
    electron_protobuf_repository(
        name = "electron_protobuf_sources",
        chromium = "@electron_chromium_sources//:DEPS",
        javascript = "@electron_protobuf_javascript_upstream//:BUILD.bazel",
    )
    support_repos = []
    for name, github, revision, sha256 in [
        ("dragonbox", "jk-jeon/dragonbox", "6c7c925b571d54486b9ffae8d9d18a822801cbda", "71f2ed97cf89cc6b05c0aefb349bd137f521eca4e27f0fe985b1a815a77889a6"),
        ("fast_float", "fastfloat/fast_float", "cb1d42aaa1e14b09e1452cfdef373d051b8c02a4", "68faac8220af2d346bc76c71a6baad4a0e692640d9a595606a745219757fccdc"),
        ("highway", "google/highway", "84379d1c73de9681b54fbe1c035a23c7bd5d272d", "1647ed8ba0a614347e2e9d34e7957a2547387997255a559e469ef04b0bc520a0"),
    ]:
        repo = "electron_" + name + "_upstream"
        http_archive(
            name = repo,
            urls = ["https://github.com/" + github + "/archive/" + revision + ".tar.gz"],
            sha256 = sha256,
            strip_prefix = name + "-" + revision,
            build_file_content = "exports_files([\"BUILD.bazel\"], visibility = [\"//visibility:public\"])\n",
        )
        support_repos.append(repo)
    electron_v8_support_repository(
        name = "electron_v8_support_sources",
        chromium = "@electron_chromium_sources//:DEPS",
        dragonbox = "@electron_dragonbox_upstream//:BUILD.bazel",
        fast_float = "@electron_fast_float_upstream//:BUILD.bazel",
        highway = "@electron_highway_upstream//:BUILD.bazel",
    )
    electron_node_repository(name = "electron_node_sources", electron = "@electron//:DEPS")
    direct = ["electron_libnode_sources", "electron_zstd_upstream", "electron_base_sources", "electron_lss_upstream", "electron_node_sources", "electron_v8_sources", "electron_chromium_sources", "electron_cast_core_sources", "electron_glslang_sources", "electron_abseil_sources", "electron_icu_sources", "electron_partition_alloc_sources", "electron_rust_sources", "electron_v8_support_sources", "electron_protobuf_sources", "electron_protobuf_javascript_upstream", "electron_perfetto_native_sources", "electron_jsoncpp_upstream", "electron_v8_engine_sources", "electron_fp16_upstream"] + dependency_repos + support_repos
    return ctx.extension_metadata(reproducible = True, root_module_direct_deps = direct, root_module_direct_dev_deps = [])

electron = module_extension(implementation = _impl, tag_classes = {"version": tag_class(attrs = {"version": attr.string(mandatory = True)})})

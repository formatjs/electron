"""Exact, patched dependencies for the Electron source overlay."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository", "new_git_repository")
load(":archive_urls.bzl", http_archive = "electron_source_archive")
load(":base_repository.bzl", "electron_base_repository")
load(":codecs_repository.bzl", "electron_codecs_repository")
load(":display_repository.bzl", "electron_display_repository")
load(":embedder_repository.bzl", "electron_embedder_repository")
load(":events_repository.bzl", "electron_events_repository")
load(":fonts_repository.bzl", "electron_fonts_repository")
load(":gfx_repository.bzl", "electron_gfx_repository")
load(":icu_repository.bzl", "electron_icu_repository")
load(":ipcz_repository.bzl", "electron_ipcz_repository")
load(":libnode_repository.bzl", "electron_libnode_repository")
load(":mojo_repository.bzl", "electron_mojo_repository")
load(":network_repository.bzl", "electron_network_repository")
load(":overlay_repository.bzl", "electron_overlay_archive", "electron_overlay_repository")
load(":partition_alloc_repository.bzl", "electron_partition_alloc_repository")
load(":perfetto_repository.bzl", "electron_perfetto_repository")
load(":platform_repository.bzl", "electron_platform_repositories")
load(":protobuf_repository.bzl", "electron_protobuf_repository")
load(":rust_repository.bzl", "electron_rust_repository")
load(":skia_repository.bzl", "electron_skia_repository")
load(":source_repositories.bzl", "electron_abseil_repository", "electron_node_repository", "electron_patched_upstream")
load(":ui_repository.bzl", "electron_ui_repository")
load(":v8_engine_repository.bzl", "electron_v8_engine_repository")
load(":v8_support_repository.bzl", "electron_v8_support_repository")
load(":xcb_repository.bzl", "electron_xcb_repository")

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
            git_repository(name = name, remote = remote, commit = commit, patches = patches + [Label("//source:boringssl-electron.patch"), Label("//source:boringssl-chromium.patch")], patch_strip = 1)
        else:
            new_git_repository(name = name, remote = remote, commit = commit, patches = patches, patch_strip = 1, build_file_content = "package(default_visibility = [\"//visibility:public\"])\n" + ("exports_files([\"BUILD.gn\"])\n" if group == "perfetto" else "") + "filegroup(name = \"source_anchor\", srcs = glob([\"*\"], exclude = [\"BUILD.bazel\"]))")
        dependency_repos.append(name)
    electron_abseil_repository(name = "electron_abseil_sources", chromium = "@electron_chromium_sources//:DEPS")
    electron_icu_repository(name = "electron_icu_sources", chromium = "@electron_chromium_sources//:DEPS")
    electron_partition_alloc_repository(name = "electron_partition_alloc_sources", chromium = "@electron_chromium_sources//:DEPS")
    crabby = json.decode(ctx.read(Label("//source/native:temporal_inputs.json")))["crabbyavif_source"]
    new_git_repository(
        name = "electron_crabbyavif_upstream",
        remote = crabby["remote"],
        commit = crabby["commit"],
        build_file_content = "exports_files([\"LICENSE\"], visibility = [\"//visibility:public\"])\n",
    )
    electron_rust_repository(name = "electron_rust_sources", chromium = "@electron_chromium_sources//:DEPS", fontconfig = "@electron_fontconfig_upstream//:COPYING", skia = "@electron_skia_upstream//:LICENSE", crabbyavif = "@electron_crabbyavif_upstream//:LICENSE")
    http_archive(
        name = "electron_lss_upstream",
        urls = ["https://github.com/citizenfx/linux-syscall-support/archive/ed31caa60f20a4f6569883b2d752ef7522de51e0.tar.gz"],
        integrity = "sha256-KE6rt4Lt3wvLrjNSL/lxwepRYUlWqA500k4od6o9oAA=",
        strip_prefix = "linux-syscall-support-ed31caa60f20a4f6569883b2d752ef7522de51e0",
        build_file_content = "exports_files([\"LICENSE\"], visibility = [\"//visibility:public\"])\n",
    )
    electron_base_repository(name = "electron_base_sources", chromium = "@electron_chromium_sources//:DEPS", lss = "@electron_lss_upstream//:LICENSE")
    electron_ipcz_repository(name = "electron_ipcz_sources", chromium = "@electron_chromium_sources//:DEPS")
    http_archive(
        name = "electron_chromium_native_support",
        urls = ["https://github.com/formatjs/chromium/archive/4a2321d1086a36b4bb99ec237a379827b784b0b0.tar.gz"],
        sha256 = "45c37819be5d4472d01f101088b651c40ff1d80b49f333ebee7626a1512fc522",
        strip_prefix = "chromium-4a2321d1086a36b4bb99ec237a379827b784b0b0",
    )
    for name in ["nspr", "nss"]:
        archive = "electron_" + name + "_upstream"
        electron_overlay_archive(name = archive, catalog = "@electron_chromium_native_support//:overlays.json", overlay = name)
        electron_overlay_repository(name = name, archive = "@" + archive + "//__source__:anchor", catalog = "@electron_chromium_native_support//:overlays.json", overlay = name, patches = [Label("//source:nss_integrity.patch" if name == "nss" else "//source:nspr_runtime.patch")])
    for name, github, revision, digest, anchor in [
        ("quiche", "google/quiche", "c0df0d316bd7e4ddf44e5ba094b5c5b061d94b0c", "23e9c360d3a42e8d9cd006e0fcafebe9387e9f72bd722d5a0d0ba92ca349b110", "LICENSE"),
        ("re2", "google/re2", "cd7b2823a8375371f7efe6dae17837c9ab407693", "84f9ced9bb4b1fab2f5c061bf136030d5128e79cfe56b3bc3bde8e20de7e25db", "LICENSE"),
    ]:
        http_archive(
            name = "electron_" + name + "_upstream",
            urls = ["https://github.com/" + github + "/archive/" + revision + ".tar.gz"],
            sha256 = digest,
            strip_prefix = name + "-" + revision,
            build_file_content = "exports_files([" + repr(anchor) + "], visibility = [\"//visibility:public\"])\n",
        )
    http_archive(
        name = "electron_network_platform_headers",
        urls = ["https://commondatastorage.googleapis.com/chrome-linux-sysroot/36a164623d03f525e3dfb783a5e9b8a00e98e1ddd2b5cff4e449bd016dd27e50"],
        sha256 = "36a164623d03f525e3dfb783a5e9b8a00e98e1ddd2b5cff4e449bd016dd27e50",
        type = "tar.xz",
        build_file_content = 'load("@rules_cc//cc:cc_library.bzl", "cc_library")\ncc_library(name = "gssapi", hdrs = ["usr/include/mit-krb5/gssapi.h", "usr/include/mit-krb5/gssapi/gssapi.h"], includes = ["usr/include/mit-krb5"], visibility = ["//visibility:public"])\ncc_library(name = "graphics", hdrs = glob(["usr/include/X11/**/*.h", "usr/include/xcb/**/*.h", "usr/include/GL/**/*.h", "usr/include/EGL/**/*.h", "usr/include/KHR/**/*.h"]), strip_include_prefix = "usr/include", visibility = ["//visibility:public"])\n',
    )
    for name, url, digest, anchor, strip in [
        ("fontconfig", "https://github.com/fontconfig/fontconfig/archive/f0ed9c3f43161d3555f6f7a5234b22fe7ca60727.tar.gz", "8d0a35fa74c30a7ca8774efaa3e2fb73b9aa6caf49354e425011ba61b8e15280", "COPYING", "fontconfig-f0ed9c3f43161d3555f6f7a5234b22fe7ca60727"),
        ("freetype", "https://github.com/freetype/freetype/archive/d3668e00da732654b50e4e81f982544ed6e26390.tar.gz", "0411bbbfa77b4ecb0664e98341ce79432547e551377e66e142b3f94884fe6289", "LICENSE.TXT", "freetype-d3668e00da732654b50e4e81f982544ed6e26390"),
        ("harfbuzz", "https://github.com/harfbuzz/harfbuzz/archive/7d936359a27abb2d7cb14ecc102463bb15c11843.tar.gz", "88468a169694565a7504a9aa16ffa42309ee72cb7205c46b8e071dc419ac62a8", "COPYING", "harfbuzz-7d936359a27abb2d7cb14ecc102463bb15c11843"),
    ]:
        exported = [anchor] + (["test/shape/data/in-house/fonts/7bbd3175734d5d291e1c15271ec0cbb97b626ebf.ttf"] if name == "harfbuzz" else [])
        http_archive(name = "electron_" + name + "_upstream", urls = [url], sha256 = digest, strip_prefix = strip, build_file_content = "exports_files(" + repr(exported) + ", visibility = [\"//visibility:public\"])\n")
    for name, remote, commit, anchor in [
        ("jpeg", "https://chromium.googlesource.com/chromium/deps/libjpeg_turbo.git", "e14cbfaa85529d47f9f55b0f104a579c1061f9ad", "LICENSE.md"),
        ("nasm", "https://chromium.googlesource.com/chromium/deps/nasm.git", "e2c93c34982b286b27ce8b56dd7159e0b90869a2", "LICENSE"),
    ]:
        new_git_repository(name = "electron_" + name + "_upstream", remote = remote, commit = commit, build_file_content = "exports_files([" + repr(anchor) + "], visibility = [\"//visibility:public\"])\n")
    for name, github, commit, digest, anchor in [
        ("webp", "webmproject/libwebp", "b0e8039062eedbcb20ebb1bad62bfeaee2b94ec6", "5e085cf7e7e5e7fe5373c9e1c1ef31e6d7b89f67ab2d26fb9d542abb5d718939", "COPYING"),
        ("wuffs", "google/wuffs-mirror-release-c", "e3f919ccfe3ef542cfc983a82146070258fb57f8", "e849dab1f372f16b782ba7528e7f70281e35425bd2d644c92a36fb95909f98db", "LICENSE"),
    ]:
        http_archive(name = "electron_" + name + "_upstream", urls = ["https://github.com/" + github + "/archive/" + commit + ".tar.gz"], sha256 = digest, strip_prefix = ("libwebp" if name == "webp" else "wuffs-mirror-release-c") + "-" + commit, build_file_content = "exports_files([" + repr(anchor) + "], visibility = [\"//visibility:public\"])\n")
    for name, github, commit, digest, prefix, anchor in [
        ("skia", "google/skia", "f4ed99d2443962782cf5f8b4dd27179f131e7cbe", "1f273c735a430bb3c8e770b80d23dea88cea346f705c6028912ab3849c18bbc6", "skia", "LICENSE"),
        ("dawn", "google/dawn", "cee9cb0d67e749bf42f5e90cb3b8a6f525dbb920", "604b16af14b41e2485df4d9e65f749d649e5c25729a1de43569b41e63249a16e", "dawn", "LICENSE"),
        ("vulkan", "KhronosGroup/Vulkan-Headers", "a4f8ada9f4f97c45b8c89c57997be9cebaae65d2", "0b0f6517f579181a8d9319adeab6aceb51d2b9497c35c436b95af0dae109a7f1", "Vulkan-Headers", "LICENSE.md"),
    ]:
        http_archive(name = "electron_" + name + "_upstream", urls = ["https://github.com/" + github + "/archive/" + commit + ".tar.gz"], sha256 = digest, strip_prefix = prefix + "-" + commit, build_file_content = "exports_files([" + repr(anchor) + "], visibility = [\"//visibility:public\"])\n")
    for name, remote, commit, anchor in [
        ("libdrm", "https://chromium.googlesource.com/chromiumos/third_party/libdrm.git", "ad78bb591d02162d3b90890aa4d0a238b2a37cde", "xf86drm.h"),
        ("libsync", "https://chromium.googlesource.com/aosp/platform/system/core/libsync.git", "f4f4387b6bf2387efbcfd1453af4892e8982faf6", "sync.c"),
    ]:
        new_git_repository(name = "electron_" + name + "_upstream", remote = remote, commit = commit, build_file_content = "exports_files([" + repr(anchor) + "], visibility = [\"//visibility:public\"])\n")
    for name, remote, commit, anchor in [
        ("snappy", "https://chromium.googlesource.com/external/github.com/google/snappy.git", "32ded457c0b1fe78ceb8397632c416568d6714a0", "COPYING"),
    ]:
        new_git_repository(name = "electron_" + name + "_upstream", remote = remote, commit = commit, build_file_content = "exports_files([" + repr(anchor) + "], visibility = [\"//visibility:public\"])\n")
    http_archive(
        name = "electron_chromium_webui_upstream",
        urls = ["https://storage.googleapis.com/chromium-nodejs/e882f4f8be7b5fb8446e8f73ab1c49337f69dfb4?generation=1754921648984973"],
        sha256 = "8b94d7c9daec96b6641175a1165afb288d0bfec967f26ece31be05b46302a4f6",
        type = "tar.gz",
        add_prefix = "node_modules",
        build_file_content = "exports_files([\"BUILD.bazel\"], visibility = [\"//visibility:public\"])\n",
    )
    http_archive(
        name = "electron_chromium_node_tool",
        urls = ["https://storage.googleapis.com/chromium-nodejs/fa98c6432de572206bc5519f85e9c96bd518b039?generation=1730835522207929"],
        sha256 = "fb563633b5bfe2d4307075c54c6bb54664a3b5ec6bc811f5b15742720549007a",
        type = "tar.gz",
        build_file_content = "exports_files([\"node-linux-x64/bin/node\"], visibility = [\"//visibility:public\"])\n",
    )
    platform_repos = electron_platform_repositories(ctx)
    electron_ui_repository(name = "electron_ui_sources", chromium = "@electron_chromium_sources//:DEPS", node_modules = "@electron_chromium_webui_upstream//:BUILD.bazel")
    electron_ui_repository(name = "electron_content_webui_sources", chromium = "@electron_chromium_sources//:DEPS", node_modules = "@electron_chromium_webui_upstream//:BUILD.bazel", profile = "//source/native:content_webui_inputs.json", build_file = "//source:content_webui.BUILD.bazel", source_roots = {
        "@electron//:DEPS": "electron",
        "@electron_platform_dom_distiller_js_dist//:BUILD.bazel": "third_party/dom_distiller_js/dist",
        "@electron_platform_readability_src//:BUILD.bazel": "third_party/readability/src",
    })
    electron_xcb_repository(name = "electron_xcb_sources", source = "@libxcb//:BUILD.bazel", protocol = "@xcb-proto//:COPYING")
    electron_events_repository(name = "electron_events_sources", chromium = "@electron_chromium_sources//:DEPS", snappy = "@electron_snappy_upstream//:COPYING", protobuf_javascript = "@electron_protobuf_javascript_upstream//:BUILD.bazel", perfetto = "@electron_perfetto_sources//:BUILD.gn")
    electron_display_repository(name = "electron_display_sources", chromium = "@electron_chromium_sources//:DEPS")
    electron_gfx_repository(name = "electron_gfx_sources", chromium = "@electron_chromium_sources//:DEPS", libdrm = "@electron_libdrm_upstream//:xf86drm.h", libsync = "@electron_libsync_upstream//:sync.c")
    electron_skia_repository(name = "electron_skia_sources", chromium = "@electron_chromium_sources//:DEPS", skia = "@electron_skia_upstream//:LICENSE", dawn = "@electron_dawn_upstream//:LICENSE", vulkan = "@electron_vulkan_upstream//:LICENSE.md")
    electron_codecs_repository(name = "electron_codecs_sources", chromium = "@electron_chromium_sources//:DEPS", jpeg = "@electron_jpeg_upstream//:LICENSE.md", webp = "@electron_webp_upstream//:COPYING", wuffs = "@electron_wuffs_upstream//:LICENSE", nasm = "@electron_nasm_upstream//:LICENSE")
    electron_fonts_repository(name = "electron_fonts_sources", chromium = "@electron_chromium_sources//:DEPS", freetype = "@electron_freetype_upstream//:LICENSE.TXT", harfbuzz = "@electron_harfbuzz_upstream//:COPYING", fontconfig = "@electron_fontconfig_upstream//:COPYING")
    electron_mojo_repository(name = "electron_mojo_sources", chromium = "@electron_chromium_sources//:DEPS")
    electron_network_repository(
        name = "electron_network_sources",
        chromium = "@electron_chromium_sources//:DEPS",
        quiche = "@electron_quiche_upstream//:LICENSE",
        re2 = "@electron_re2_upstream//:LICENSE",
        sqlite = "@electron_sqlite_sources//:LICENSE.md",
    )
    http_archive(
        name = "electron_ced_upstream",
        urls = ["https://github.com/google/compact_enc_det/archive/ba412eaaacd3186085babcd901679a48863c7dd5.tar.gz"],
        integrity = "sha256-osln5ApPlEjor46cJZSpvFF/qdSRtw4i8cl7NfJrrLI=",
        strip_prefix = "compact_enc_det-ba412eaaacd3186085babcd901679a48863c7dd5",
        build_file_content = "exports_files([\"LICENSE\"], visibility = [\"//visibility:public\"])\n",
    )
    electron_embedder_repository(name = "electron_embedder_sources", chromium = "@electron_chromium_sources//:DEPS", ced = "@electron_ced_upstream//:LICENSE")
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
    direct = ["electron_embedder_sources", "electron_ced_upstream", "electron_libnode_sources", "electron_zstd_upstream", "electron_base_sources", "electron_lss_upstream", "electron_node_sources", "electron_v8_sources", "electron_chromium_sources", "electron_cast_core_sources", "electron_glslang_sources", "electron_abseil_sources", "electron_icu_sources", "electron_partition_alloc_sources", "electron_rust_sources", "electron_crabbyavif_upstream", "electron_v8_support_sources", "electron_protobuf_sources", "electron_protobuf_javascript_upstream", "electron_perfetto_native_sources", "electron_jsoncpp_upstream", "electron_v8_engine_sources", "electron_fp16_upstream"] + dependency_repos + support_repos
    return ctx.extension_metadata(reproducible = True, root_module_direct_deps = direct + platform_repos + ["electron_content_webui_sources", "electron_ui_sources", "electron_chromium_webui_upstream", "electron_chromium_node_tool", "electron_xcb_sources", "electron_events_sources", "electron_snappy_upstream", "electron_display_sources", "electron_gfx_sources", "electron_libdrm_upstream", "electron_libsync_upstream", "electron_skia_sources", "electron_skia_upstream", "electron_dawn_upstream", "electron_vulkan_upstream", "electron_codecs_sources", "electron_jpeg_upstream", "electron_webp_upstream", "electron_wuffs_upstream", "electron_nasm_upstream", "electron_fontconfig_upstream", "electron_freetype_upstream", "electron_harfbuzz_upstream", "electron_fonts_sources", "electron_mojo_sources", "electron_ipcz_sources", "electron_chromium_native_support", "electron_nspr_upstream", "electron_nss_upstream", "nspr", "nss", "electron_quiche_upstream", "electron_re2_upstream", "electron_network_platform_headers", "electron_network_sources"], root_module_direct_dev_deps = [])

electron = module_extension(implementation = _impl, tag_classes = {"version": tag_class(attrs = {"version": attr.string(mandatory = True)})})

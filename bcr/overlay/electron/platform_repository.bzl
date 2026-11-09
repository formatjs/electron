"""Exact platform sources and the pinned Linux desktop SDK/runtime closure."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "new_git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load(":credits_repository.bzl", "electron_credits_repository")
load(":profile_codec.bzl", "unpack_profile")

def _sources_impl(ctx):
    ctx.read(ctx.attr.chromium)
    chromium = ctx.path(ctx.attr.chromium).dirname
    roots = {}
    for anchor, prefix in ctx.attr.sources.items():
        ctx.read(anchor)
        roots[prefix] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = unpack_profile(json.decode(contents))
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid platform source path")
        source = chromium.get_child(path)
        matched = 0
        for prefix, root in roots.items():
            if len(prefix) > matched and path.startswith(prefix + "/"):
                source = root.get_child(path[len(prefix) + 1:])
                matched = len(prefix)
        if not source.exists:
            fail("Pinned platform source missing: " + path)
        if path in ["build/util/lastchange.py", "tools/json_to_struct/json_to_struct.py", "content/browser/cookie_store/cookie_store_manager.cc", "printing/backend/mojom/print_backend_mojom_traits.cc", "components/autofill/core/browser/metrics/quality_metrics.cc", "electron/shell/common/asar/archive.cc", "electron/shell/common/node_util.cc"]:
            ctx.file(path, ctx.read(source), executable = False)
        else:
            ctx.symlink(source, path)
    ctx.patch(ctx.attr.lastchange_patch, strip = 1)
    ctx.patch(ctx.attr.json_year_patch, strip = 1)
    ctx.patch(ctx.attr.cookie_projection_patch, strip = 1)
    ctx.patch(ctx.attr.printing_comparator_patch, strip = 1)
    ctx.patch(ctx.attr.autofill_projection_patch, strip = 1)
    ctx.patch(ctx.attr.asar_canonical_paths_patch, strip = 1)
    ctx.patch(ctx.attr.node_builtin_loader_patch, strip = 1)
    ctx.file("native_compat_patches.json", json.encode({"graph_sha256": profile["graph_sha256"], "patches": [str(ctx.attr.lastchange_patch), str(ctx.attr.json_year_patch), str(ctx.attr.cookie_projection_patch), str(ctx.attr.printing_comparator_patch), str(ctx.attr.autofill_projection_patch), str(ctx.attr.asar_canonical_paths_patch), str(ctx.attr.node_builtin_loader_patch)], "files": ["build/util/lastchange.py", "tools/json_to_struct/json_to_struct.py", "content/browser/cookie_store/cookie_store_manager.cc", "printing/backend/mojom/print_backend_mojom_traits.cc", "components/autofill/core/browser/metrics/quality_metrics.cc", "electron/shell/common/asar/archive.cc", "electron/shell/common/node_util.cc"]}))
    for path, content in profile["generated_files"].items():
        if not path.startswith("//out/bazel-import/") or ".." in path.split("/"):
            fail("Invalid platform metadata path")
        ctx.file(path[2:], content, executable = False)
    ctx.file("profile.bzl", 'load("@electron//electron:profile_codec.bzl", "unpack_profile")\nPROFILE = unpack_profile(json.decode(' + json.encode(contents) + "))\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

_platform_sources = repository_rule(
    implementation = _sources_impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "printing_comparator_patch": attr.label(default = Label("//source:printing_comparator.patch")),
        "asar_canonical_paths_patch": attr.label(default = Label("//source:asar_canonical_paths.patch")),
        "node_builtin_loader_patch": attr.label(default = Label("//source:node_builtin_loader.patch")),
        "autofill_projection_patch": attr.label(default = Label("//source:autofill_projection.patch")),
        "cookie_projection_patch": attr.label(default = Label("//source:cookie_subscription_projection.patch")),
        "json_year_patch": attr.label(default = Label("//source:json_to_struct_year.patch")),
        "lastchange_patch": attr.label(default = Label("//source:lastchange_environment.patch")),
        "sources": attr.label_keyed_string_dict(mandatory = True),
        "profile": attr.label(default = Label("//source/native:platform_inputs.json")),
        "build_file": attr.label(default = Label("//source:platform.BUILD.bazel")),
    },
)

def _runtime_impl(ctx):
    contents = ctx.read(ctx.attr.manifest)
    manifest = json.decode(contents)
    host_abi = ["ld-linux-x86-64.so.2", "libc.so.6", "libdl.so.2", "libgcc_s.so.1", "libm.so.6", "libpthread.so.0", "libresolv.so.2", "librt.so.1", "libstdc++.so.6", "libutil.so.1"]
    for name, library in manifest["libraries"].items():
        for needed in library["needed"]:
            if needed not in manifest["libraries"] and needed not in host_abi:
                fail("Undeclared SDK runtime dependency: " + name + " needs " + needed)
    for package in manifest["packages"]:
        name = package["url"].split("/")[-1].split("_")[0]
        archive = "packages/" + name
        ctx.download_and_extract(url = package.get("urls", [package["url"]]), sha256 = package["sha256"], type = "deb", output = archive)
        payloads = [ctx.path(archive + "/" + filename) for filename in ["data.tar.xz", "data.tar.gz", "data.tar.zst", "data.tar.bz2"] if ctx.path(archive + "/" + filename).exists]
        if len(payloads) != 1:
            fail("Expected one pinned Debian data archive")
        ctx.extract(payloads[0], output = archive + "/root")
    for soname, library in manifest["libraries"].items():
        ctx.symlink("packages/" + library["package"] + "/root/" + library["interface"], soname)
    copyrights = manifest.get("copyrights", {})
    for name, notice in copyrights.items():
        ctx.symlink("packages/" + notice["package"] + "/root/" + notice["path"], "licenses/" + name)
    common = manifest.get("common_licenses", {})
    for name, notice in common.items():
        ctx.symlink("packages/" + notice["package"] + "/root/" + notice["path"], "licenses/common/" + name)
    needed = {name: library["needed"] for name, library in manifest["libraries"].items()}
    ctx.file("profile.bzl", "LIBRARIES = " + repr(sorted(manifest["libraries"])) + "\nNEEDED = " + repr(needed) + "\nCOPYRIGHTS = " + repr(copyrights) + "\nCOMMON_LICENSES = " + repr(common) + "\n")
    build = [
        'load("@rules_cc//cc:cc_library.bzl", "cc_library")',
        'package(default_visibility = ["//visibility:public"])',
        "exports_files(" + repr(sorted(manifest["libraries"]) + ["licenses/" + name for name in copyrights] + ["licenses/common/" + name for name in common] + ["profile.bzl"]) + ")",
        "filegroup(name = \"libraries\", srcs = " + repr(sorted(manifest["libraries"])) + ")",
    ]
    for name, interface in manifest.get("header_interfaces", {}).items():
        root = "packages/" + interface["package"] + "/root/"
        build.append("cc_library(name = " + repr(name) + ", hdrs = " + repr([root + path for path in interface["headers"]]) + ", includes = " + repr([root + interface["include"]]) + ', deps = ["@electron_platform_sdk//:headers"])')
    ctx.file("BUILD.bazel", "\n".join(build) + "\n")

_platform_runtime = repository_rule(
    implementation = _runtime_impl,
    attrs = {"manifest": attr.label(default = Label("//source/native:platform_runtime.json"))},
)

def electron_platform_repositories(ctx):
    profile = unpack_profile(json.decode(ctx.read(Label("//source/native:platform_inputs.json"))))
    anchors, names = {"@electron//:DEPS": "electron"}, []
    for prefix, pin in profile["source_revisions"].items():
        group = pin.get("patch_group")
        if group in ["ffmpeg", "webrtc", "devtools_frontend", "perfetto"]:
            original = [entry for entry in json.decode(ctx.read(Label("//source:upstream_pins.json"))) if entry["group"] == group][0]
            if original["url"] != pin["remote"] + "@" + pin["commit"]:
                fail("Platform revision differs from Electron's patched source: " + group)
            anchors["@electron_" + group + "_sources//:BUILD.bazel"] = prefix
            continue
        suffix = prefix[len("third_party/"):] if prefix.startswith("third_party/") else prefix
        name = "electron_platform_" + suffix.replace("-", "_").replace("/", "_").lower()
        build_file_content = "exports_files([\"BUILD.bazel\"], visibility = [\"//visibility:public\"])\n"
        if pin.get("archive"):
            archive = pin["archive"]
            http_archive(name = name, urls = [archive["url"]], sha256 = archive["sha256"], strip_prefix = archive["strip_prefix"], type = "tar.gz", build_file_content = build_file_content)
        else:
            new_git_repository(name = name, remote = pin["remote"], commit = pin["commit"], build_file_content = build_file_content)
        anchors["@" + name + "//:BUILD.bazel"] = prefix
        names.append(name)
    esbuild = profile["devtools_esbuild"]
    http_archive(
        name = "electron_platform_esbuild",
        urls = [esbuild["url"]],
        sha256 = esbuild["sha256"],
        type = "zip",
        build_file_content = "exports_files([\"esbuild\"], visibility = [\"//visibility:public\"])\n",
    )
    names.append("electron_platform_esbuild")
    _platform_sources(name = "electron_platform_sources", chromium = "@electron_chromium_sources//:DEPS", sources = anchors)
    inventory = json.decode(ctx.read(Label("//source/native:credits_inputs.json")))
    if inventory["source_revisions"] != profile["source_revisions"]:
        fail("Recapture credits after changing platform source revisions")
    electron_credits_repository(name = "electron_credits_sources", chromium = "@electron_chromium_sources//:DEPS", sources = anchors)
    _platform_runtime(name = "electron_platform_runtime")
    http_archive(
        name = "electron_platform_sdk",
        urls = ["https://commondatastorage.googleapis.com/chrome-linux-sysroot/36a164623d03f525e3dfb783a5e9b8a00e98e1ddd2b5cff4e449bd016dd27e50"],
        sha256 = "36a164623d03f525e3dfb783a5e9b8a00e98e1ddd2b5cff4e449bd016dd27e50",
        type = "tar.xz",
        build_file = Label("//source:platform_sdk.BUILD.bazel"),
    )
    http_archive(
        name = "electron_platform_pciutils",
        urls = ["https://www.kernel.org/pub/software/utils/pciutils/pciutils-3.7.0.tar.xz"],
        sha256 = "9d40b97be8b6a2cdf96aead5a61881d1f7e4e0da9544a9bac4fba1ae9dcd40eb",
        strip_prefix = "pciutils-3.7.0",
        build_file = Label("//source:pciutils.BUILD.bazel"),
    )
    return names + ["electron_platform_sources", "electron_platform_runtime", "electron_platform_sdk", "electron_platform_pciutils", "electron_credits_sources"]

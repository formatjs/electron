"""Exact platform sources and the pinned Linux desktop SDK/runtime closure."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "new_git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

def _sources_impl(ctx):
    ctx.read(ctx.attr.chromium)
    chromium = ctx.path(ctx.attr.chromium).dirname
    roots = {}
    for anchor, prefix in ctx.attr.sources.items():
        ctx.read(anchor)
        roots[prefix] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
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
        if path in ["build/util/lastchange.py", "tools/json_to_struct/json_to_struct.py"]:
            ctx.file(path, ctx.read(source), executable = False)
        else:
            ctx.symlink(source, path)
    ctx.patch(ctx.attr.lastchange_patch, strip = 1)
    ctx.patch(ctx.attr.json_year_patch, strip = 1)
    ctx.file("native_compat_patches.json", json.encode({"graph_sha256": profile["graph_sha256"], "patches": [str(ctx.attr.lastchange_patch), str(ctx.attr.json_year_patch)], "files": ["build/util/lastchange.py", "tools/json_to_struct/json_to_struct.py"]}))
    for path, content in profile["generated_files"].items():
        if not path.startswith("//out/bazel-import/") or ".." in path.split("/"):
            fail("Invalid platform metadata path")
        ctx.file(path[2:], content, executable = False)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

_platform_sources = repository_rule(
    implementation = _sources_impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
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
    ctx.file("profile.bzl", "LIBRARIES = " + repr(sorted(manifest["libraries"])) + "\n")
    ctx.file("BUILD.bazel", "exports_files(" + repr(sorted(manifest["libraries"]) + ["profile.bzl"]) + ", visibility = [\"//visibility:public\"])\nfilegroup(name = \"libraries\", srcs = " + repr(sorted(manifest["libraries"])) + ", visibility = [\"//visibility:public\"])\n")

_platform_runtime = repository_rule(
    implementation = _runtime_impl,
    attrs = {"manifest": attr.label(default = Label("//source/native:platform_runtime.json"))},
)

def electron_platform_repositories(ctx):
    profile = json.decode(ctx.read(Label("//source/native:platform_inputs.json")))
    anchors, names = {"@electron//:DEPS": "electron"}, []
    for prefix, pin in profile["source_revisions"].items():
        group = pin.get("patch_group")
        if group in ["ffmpeg", "webrtc", "devtools_frontend"]:
            original = [entry for entry in json.decode(ctx.read(Label("//source:upstream_pins.json"))) if entry["group"] == group][0]
            if original["url"] != pin["remote"] + "@" + pin["commit"]:
                fail("Platform revision differs from Electron's patched source: " + group)
            anchors["@electron_" + group + "_sources//:BUILD.bazel"] = prefix
            continue
        suffix = prefix[len("third_party/"):] if prefix.startswith("third_party/") else prefix
        name = "electron_platform_" + suffix.replace("-", "_").replace("/", "_").lower()
        new_git_repository(name = name, remote = pin["remote"], commit = pin["commit"], build_file_content = "exports_files([\"BUILD.bazel\"], visibility = [\"//visibility:public\"])\n")
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
    return names + ["electron_platform_sources", "electron_platform_runtime", "electron_platform_sdk", "electron_platform_pciutils"]

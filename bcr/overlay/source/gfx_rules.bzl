"""Complete matching gfx, geometry/range wire types and native graphics dependencies."""

load("@electron_gfx_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(original):
    return PROFILE["external"].get(original, ":" + PROFILE["names"].get(original, ""))

def _file(original):
    if original in PROFILE["external_files"]:
        return PROFILE["external_files"][original]
    if original in PROFILE["generated_files"]:
        return "//:" + original[2:]
    return ":" + original[len(_BUILD):] if original.startswith(_BUILD) else "//:" + original[2:]

def electron_gfx():
    native.exports_files(PROFILE["files"] + [path[2:] for path in PROFILE["generated_files"]] + ["profile.bzl", "BUILD.bazel"])
    cc_library(
        name = "source_headers",
        hdrs = {_file("//" + path): True for headers in PROFILE["headers"].values() for path in headers}.keys() + [_file(path) for action in PROFILE["actions"].values() for path in action["outputs"] if path.endswith(".h")],
        textual_hdrs = [_file("//" + path) for path in PROFILE["textual_headers"]],
        includes = [".", "gen", "third_party/libdrm/src", "third_party/libdrm/src/include", "third_party/libdrm/src/include/drm", "third_party/libsync/src/include"],
        deps = ["@electron_skia_sources//:source_headers", "@electron_mojo_sources//:bindings", "@electron_partition_alloc_sources//:raw_ptr"],
        target_compatible_with = _COMPATIBLE,
    )
    for original, action in PROFILE["actions"].items():
        outputs = [path[len(_BUILD):] for path in action["outputs"]]
        electron_source_action(
            name = action["name"] + "_run",
            srcs = {_file(path): path[2:] for path in action["inputs"]},
            script = action["script"],
            args = action["args"],
            response = action["response"],
            out_files = outputs,
            logical_outputs = outputs,
            target_compatible_with = _COMPATIBLE,
        )
        cc_library(
            name = action["name"],
            hdrs = [_file(path) for path in action["outputs"] if path.endswith(".h")],
            textual_hdrs = [_file(path) for path in action["outputs"] if path.endswith((".inc", ".cc"))],
            data = [_file(path) for path in action["outputs"] if not path.endswith((".h", ".inc", ".cc"))],
            includes = ["gen"],
            target_compatible_with = _COMPATIBLE,
        )
    for original, metadata in PROFILE["metadata"].items():
        cc_library(name = metadata["name"], data = [_file(path) for path in metadata["outputs"]], target_compatible_with = _COMPATIBLE)
    for original, library in PROFILE["libraries"].items():
        settings = dict(
            hdrs = {_file(path): True for path in library["source_headers"] + library["public_headers"]}.keys(),
            textual_hdrs = [_file(path) for path in library["compiler_inputs"]],
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if name in ["m", "dl", "rt", "pthread", "resolv"]],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = [":source_headers"] + list({_label(dep): True for dep in library["gn_deps"] if dep not in PROFILE["toolchain_deps"]}),
        )
        if "expat" in library["libs"]:
            settings["deps"] += ["@libexpat//:libexpat"]
        if "uuid" in library["libs"]:
            settings["deps"] += ["@libuuid//:uuid"]
        if "glib-2.0" in library["libs"]:
            settings["deps"] += ["@glib//glib", "@glib//gmodule", "@glib//gobject"]
        if "gio-2.0" in library["libs"]:
            settings["deps"] += ["@glib//gio"]
        if "nss3" in library["libs"]:
            settings["deps"] += ["@nss//:nss"]
        for language, sources, flags in [("c", library["c_srcs"], library["c_copts"]), ("asm", library["asm_srcs"], library["asm_copts"])]:
            if sources:
                cc_library(name = library["name"] + "_" + language, srcs = [_file(path) for path in sources], copts = flags, alwayslink = library["kind"] == "source_set", **settings)
                settings["deps"] += [":" + library["name"] + "_" + language]
        cc_library(name = library["name"], srcs = [_file(path) for path in library["srcs"]], copts = library["copts"], alwayslink = library["kind"] == "source_set", **settings)
    for name, original in {"gfx": "//ui/gfx:gfx", "codec": "//ui/gfx/codec:codec", "geometry": "//ui/gfx/geometry:geometry", "geometry_mojom": "//ui/gfx/geometry/mojom:mojom", "range": "//ui/gfx/range:range", "range_mojom": "//ui/gfx/range/mojom:mojom", "memory_buffers": "//ui/gfx:memory_buffer_sources", "data_pack": "//ui/base:ui_data_pack", "libdrm": "//third_party/libdrm:libdrm", "libsync": "//third_party/libsync:libsync"}.items():
        native.alias(name = name, actual = _label(original))
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if library["srcs"] or library["c_srcs"] or library["asm_srcs"]])

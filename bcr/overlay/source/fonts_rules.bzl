"""Original FreeType, HarfBuzz, PNG and XML native libraries."""

load("@electron_fonts_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_library.bzl", "cc_library")

_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(original):
    return PROFILE["external"].get(original, ":" + PROFILE["names"].get(original, ""))

def _file(original):
    return "//:" + original[2:]

def _family(original):
    path = original[2:].split(":")[0]
    selected = ""
    for family in PROFILE["headers"]:
        if (path == family or path.startswith(family + "/")) and len(family) > len(selected):
            selected = family
    for family in [path + "/src", path + "/src/amalgamation"]:
        if family in PROFILE["headers"]:
            selected = family
    return selected.replace("/", "_") + "_headers" if selected else "common_headers"

def electron_fonts():
    native.exports_files(PROFILE["files"] + ["profile.bzl", "BUILD.bazel"])
    cc_library(name = "common_headers", includes = ["."])
    for family, headers in PROFILE["headers"].items():
        cc_library(name = family.replace("/", "_") + "_headers", hdrs = headers, textual_hdrs = PROFILE["textual_headers"][family], includes = ["."])
    fontconfig = PROFILE["libraries"]["//third_party/fontconfig:fontconfig"]
    cc_library(
        name = "fontconfig_bindgen_headers",
        hdrs = PROFILE["headers"]["third_party/fontconfig"],
        textual_hdrs = PROFILE["textual_headers"]["third_party/fontconfig"],
        includes = fontconfig["includes"],
        defines = fontconfig["defines"],
        deps = [":freetype", ":xml"],
        target_compatible_with = _COMPATIBLE,
    )
    for original, library in PROFILE["libraries"].items():
        settings = dict(
            hdrs = {_file(path): True for path in library["source_headers"] + library["public_headers"]}.keys(),
            textual_hdrs = [_file(path) for path in library["compiler_inputs"]],
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if name in ["m", "dl", "rt", "pthread", "resolv"]],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = [":" + _family(original)] + list({_label(dep): True for dep in library["gn_deps"] if dep not in PROFILE["toolchain_deps"]}),
        )
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
    for name, original in {"freetype": "//third_party/freetype:freetype", "harfbuzz": "//third_party/harfbuzz-ng:harfbuzz-ng", "png": "//third_party/libpng:libpng", "xml": "//third_party/libxml:libxml", "fontconfig": "//third_party/fontconfig:fontconfig"}.items():
        native.alias(name = name, actual = _label(original))
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if library["srcs"] or library["c_srcs"] or library["asm_srcs"]])

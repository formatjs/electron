"""Build captured Chromium IPCz source sets with native Bazel rules."""

load("@electron_ipcz_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_library.bzl", "cc_library")

_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]
_ROOT = "//third_party/ipcz/src:ipcz_chromium"

def _label(original):
    return PROFILE["external"].get(original, ":" + PROFILE["names"].get(original, ""))

def electron_ipcz():
    native.exports_files(PROFILE["files"] + ["profile.bzl", "BUILD.bazel"])
    cc_library(name = "headers", hdrs = PROFILE["headers"], includes = [".", "third_party/ipcz/include", "third_party/ipcz/src"])
    for original, library in PROFILE["libraries"].items():
        deps = [":headers"] + [_label(dep) for dep in library["gn_deps"] if dep not in PROFILE["toolchain_deps"]]
        if "glib-2.0" in library["libs"]:
            deps += ["@glib//glib", "@glib//gmodule", "@glib//gobject"]
        cc_library(
            name = library["name"],
            srcs = ["//:" + path[2:] for path in library["srcs"]],
            copts = library["copts"],
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if name in ["dl", "rt"]],
            linkstatic = True,
            alwayslink = True,
            target_compatible_with = _COMPATIBLE,
            deps = deps,
        )
    native.alias(name = "ipcz", actual = _label(_ROOT))
    native.filegroup(name = "libraries", srcs = [_label(label) for label in PROFILE["libraries"]])
    cc_library(
        name = "reference_driver",
        testonly = True,
        srcs = PROFILE["test_driver_sources"],
        copts = PROFILE["libraries"][_ROOT]["copts"],
        local_defines = PROFILE["libraries"][_ROOT]["defines"],
        target_compatible_with = _COMPATIBLE,
        deps = [":ipcz"],
    )

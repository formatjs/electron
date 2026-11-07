"""Captured Gin, Base i18n and CED with their original buildflag producers."""

load("@electron_embedder_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(original):
    return PROFILE["external"].get(original, ":" + PROFILE["names"].get(original, ""))

def electron_embedder():
    native.exports_files(PROFILE["files"] + ["profile.bzl", "BUILD.bazel"])
    for family, headers in PROFILE["headers"].items():
        cc_library(name = family + "_headers", hdrs = headers, includes = ["."])
    for original, action in PROFILE["actions"].items():
        outputs = [path[len(_BUILD):] for path in action["outputs"]]
        electron_source_action(
            name = action["name"] + "_run",
            srcs = {"//:" + action["script"]: action["script"]},
            script = action["script"],
            args = action["args"],
            response = action["response"],
            out_files = outputs,
            logical_outputs = outputs,
            target_compatible_with = _COMPATIBLE,
        )
        cc_library(name = action["name"], hdrs = [":" + path for path in outputs], includes = ["gen"], target_compatible_with = _COMPATIBLE)
    for original, library in PROFILE["libraries"].items():
        family = "gin" if original == "//gin:gin" else "i18n" if original == "//base:i18n" else "ced"
        deps = [":" + family + "_headers"] + [_label(dep) for dep in library["gn_deps"] if dep not in PROFILE["toolchain_deps"]]
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
            target_compatible_with = _COMPATIBLE,
            deps = deps,
        )
    for name, original in {"gin": "//gin:gin", "base_i18n": "//base:i18n", "ced": "//third_party/ced:ced"}.items():
        native.alias(name = name, actual = _label(original))
    native.filegroup(name = "libraries", srcs = [_label(label) for label in PROFILE["libraries"]])

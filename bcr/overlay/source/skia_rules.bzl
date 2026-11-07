"""Complete matching Skia native libraries, Dawn generators and original Rust bridges."""

load("@electron_skia_sources//:profile.bzl", "PROFILE")
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

def electron_skia():
    native.exports_files(PROFILE["files"] + [path[2:] for path in PROFILE["generated_files"]] + ["profile.bzl", "BUILD.bazel"])
    cc_library(
        name = "source_headers",
        hdrs = [_file("//" + path) for headers in PROFILE["headers"].values() for path in headers] + [_file(path) for action in PROFILE["actions"].values() for path in action["outputs"] if path.endswith(".h")],
        textual_hdrs = [_file("//" + path) for headers in PROFILE["textual_headers"].values() for path in headers],
        includes = [".", "gen", "third_party/skia", "third_party/dawn/include", "gen/third_party/dawn/include", "third_party/vulkan-headers/src/include"],
        defines = [define for define in PROFILE["libraries"]["//skia:skia"]["defines"] if define.startswith(("SK_", "VK_"))],
        deps = ["@electron_base_sources//:source_headers", "@electron_network_platform_headers//:graphics", "@electron_fonts_sources//:freetype", "@electron_fonts_sources//:harfbuzz", "@electron_fonts_sources//:fontconfig", "@electron_codecs_sources//:jpeg", "@electron_codecs_sources//:webp", "@electron_codecs_sources//:wuffs"],
        target_compatible_with = _COMPATIBLE,
    )
    for original, action in PROFILE["actions"].items():
        outputs = [path[len(_BUILD):] for path in action["outputs"]]
        electron_source_action(
            name = action["name"] + "_run",
            srcs = {_file(path): path[2:] for path in action["inputs"]},
            tools = {label: path[2:] for path, label in action["tools"].items()},
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
    for name, original in {"skia": PROFILE["root"]}.items():
        native.alias(name = name, actual = _label(original))
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if library["srcs"] or library["c_srcs"] or library["asm_srcs"]])

"""Captured patched libnode, Chromium inspector and compression implementations."""

load("@electron_libnode_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_import.bzl", "cc_import")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(original):
    return PROFILE["external"].get(original, ":" + PROFILE["names"].get(original, ""))

def _file(original):
    if original in PROFILE["generated_files"]:
        return PROFILE["generated_files"][original]
    if original.startswith(_BUILD):
        return ":" + original[len(_BUILD):]
    return "//:" + original[2:]

def _family(original):
    for name in ["brotli", "zstd", "inspector"]:
        if original.startswith("//third_party/" + ("inspector_protocol" if name == "inspector" else name) + ":"):
            return name
    return "node"

def electron_libnode():
    native.exports_files(PROFILE["files"] + ["profile.bzl", "BUILD.bazel"])
    cc_import(name = "atomic_runtime", static_library = PROFILE["native_library_replacements"]["atomic"], target_compatible_with = _COMPATIBLE)
    for family, headers in PROFILE["headers"].items():
        cc_library(name = family + "_headers", hdrs = headers, includes = ["."] + (["third_party/electron_node/src"] if family == "node" else []))
    for original, action in PROFILE["actions"].items():
        for index, run in enumerate(action["runs"]):
            outputs = [path[len(_BUILD):] for path in run["outputs"]]
            electron_source_action(
                name = action["name"] + "_run_" + str(index),
                srcs = {_file(path): path[2:] for path in run["inputs"]},
                out_files = outputs,
                logical_outputs = outputs,
                script = action["script"],
                args = run["args"],
                target_compatible_with = _COMPATIBLE,
            )
        cc_library(
            name = action["name"],
            hdrs = [_file(path) for path in action["outputs"] if path.endswith((".h", ".inc"))],
            includes = ["gen"],
            target_compatible_with = _COMPATIBLE,
        )
    for original, library in PROFILE["libraries"].items():
        settings = dict(
            hdrs = [_file(path) for path in library["generated_headers"]],
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if name in ["dl", "pthread", "rt", "m"]],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = [":" + _family(original) + "_headers"] + {_label(dep): True for dep in library["gn_deps"] + library.get("native_extra_deps", []) if dep not in PROFILE["toolchain_deps"] and dep not in PROFILE["generator_deps"]}.keys(),
        )
        if "atomic" in library["libs"]:
            settings["deps"] += [":atomic_runtime"]
        if "glib-2.0" in library["libs"]:
            settings["deps"] += ["@glib//glib", "@glib//gmodule", "@glib//gobject"]
        for language, sources, flags in [("c", library["c_srcs"], library["c_copts"]), ("asm", library["asm_srcs"], library["asm_copts"])]:
            if sources:
                cc_library(name = library["name"] + "_" + language, srcs = [_file(path) for path in sources], copts = flags, alwayslink = library["kind"] == "source_set", **settings)
                settings["deps"] += [":" + library["name"] + "_" + language]
        cc_library(name = library["name"], srcs = [_file(path) for path in library["srcs"]], copts = library["copts"], alwayslink = library["kind"] == "source_set", **settings)
    native.alias(name = "libnode", actual = _label(PROFILE["root"]))
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if library["srcs"] or library["c_srcs"] or library["asm_srcs"]])

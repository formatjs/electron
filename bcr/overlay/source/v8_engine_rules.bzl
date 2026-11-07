"""Captured full V8 engine, inspector, real snapshot compiler and runtime data."""

load("@electron_v8_engine_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:generated_layout.bzl", "electron_generated_layout")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(original):
    if original in PROFILE["external"]:
        return PROFILE["external"][original]
    return ":" + PROFILE["names"][original]

def _file(original):
    if original == _BUILD + "icudtl.dat":
        return "@electron_icu_sources//:common/icudtl.dat"
    if original.startswith(_BUILD):
        return ":" + original[len(_BUILD):]
    return "//:" + original[2:]

def _library_dep(original):
    if original in PROFILE["toolchain_deps"]:
        return False
    if original in PROFILE["libraries"] and PROFILE["libraries"][original]["kind"] == "executable":
        return False
    return True

def electron_v8_engine():
    native.exports_files(PROFILE["files"] + ["profile.bzl", "BUILD.bazel"])
    cc_library(
        name = "source_headers",
        hdrs = PROFILE["headers"],
        includes = [".", "v8", "v8/include", "third_party/fp16/src/include"],
        # GN exposes Abseil headers through include roots on header-only edges.
        deps = ["@googletest//:gtest_prod", "@electron_protobuf_sources//:abseil"],
    )
    for original, generator in PROFILE["reused_generators"].items():
        outputs = sorted(generator["outputs"])
        electron_generated_layout(
            name = generator["name"] + "_run",
            src = generator["target"],
            out_files = outputs,
            relative_inputs = [generator["outputs"][path] for path in outputs],
            target_compatible_with = _COMPATIBLE,
        )
        cc_library(
            name = generator["name"],
            hdrs = [":" + path for path in outputs if path.endswith(".h") or path.endswith(".inc")],
            includes = ["gen", "gen/v8"],
            target_compatible_with = _COMPATIBLE,
        )
    for original, action in PROFILE["actions"].items():
        outputs = [path[len(_BUILD):] for path in action["outputs"]]
        electron_source_action(
            name = action["name"] + "_run",
            srcs = {_file(path): path[2:] for path in action["inputs"]},
            tools = {_label(tool): logical for logical, tool in action["tools"].items()},
            out_files = outputs,
            logical_outputs = outputs,
            script = action["script"],
            args = action["args"],
            response = action["response"],
            deps = [":" + PROFILE["actions"][dep]["name"] + "_run" for dep in action["gn_deps"] if dep in PROFILE["actions"]],
            target_compatible_with = _COMPATIBLE,
        )
        cc_library(
            name = action["name"],
            hdrs = [":" + path for path in outputs if path.endswith(".h") or path.endswith(".inc")],
            includes = ["gen", "gen/v8"],
            target_compatible_with = _COMPATIBLE,
        )
    for original, library in PROFILE["libraries"].items():
        settings = dict(
            hdrs = [_file(path) for path in library["generated_headers"]],
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if not name.startswith("$LLVM_ROOT/")],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = [":source_headers"] + [_label(dep) for dep in library["gn_deps"] if _library_dep(dep)],
        )
        if library["asm_srcs"]:
            cc_library(name = library["name"] + "_asm", srcs = [_file(path) for path in library["asm_srcs"]], copts = library["asm_copts"], alwayslink = True, **settings)
            settings["deps"] += [":" + library["name"] + "_asm"]
        if library["kind"] == "executable":
            cc_binary(name = library["name"], srcs = [_file(path) for path in library["srcs"]] + settings.pop("hdrs"), copts = library["copts"], **settings)
        else:
            settings["defines"] = library["defines"] if original == "//v8:v8_headers" else []
            cc_library(name = library["name"], srcs = [_file(path) for path in library["srcs"]], copts = library["copts"], alwayslink = library["kind"] == "source_set", **settings)
    native.alias(name = "v8", actual = _label("//v8:v8"))
    native.alias(name = "platform", actual = _label("//v8:v8_libplatform"))
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if (library["srcs"] or library["asm_srcs"]) and library["kind"] != "executable"])
    native.filegroup(name = "runtime", srcs = [":snapshot_blob.bin", "@electron_icu_sources//:common/icudtl.dat"])

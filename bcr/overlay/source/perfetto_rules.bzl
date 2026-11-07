"""Complete captured Perfetto runtime, native plugins and original generators."""

load("@electron_perfetto_native_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(original):
    if original in PROFILE["external"]:
        return PROFILE["external"][original]
    return ":" + PROFILE["names"][original]

def _file(original):
    if original.startswith(_BUILD):
        return ":" + original[len(_BUILD):]
    if original.startswith("//third_party/protobuf/"):
        return "@electron_protobuf_sources//:" + original[2:]
    return "//:" + original[2:]

def _library_dep(original):
    if original in PROFILE["toolchain_deps"] or original == "//third_party/protobuf:protoc":
        return False
    if original in PROFILE["libraries"] and PROFILE["libraries"][original]["kind"] == "executable":
        return False
    return True

def electron_perfetto():
    native.exports_files(PROFILE["files"] + ["profile.bzl", "BUILD.bazel"])
    cc_library(
        name = "source_headers",
        hdrs = PROFILE["headers"],
        includes = [".", "third_party/perfetto", "third_party/perfetto/include", "third_party/jsoncpp/source/include"],
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
            hdrs = [":" + path for path in outputs if path.endswith(".h")],
            includes = ["gen", "gen/third_party/perfetto", "gen/third_party/perfetto/build_config"],
            target_compatible_with = _COMPATIBLE,
        )
    for original, library in PROFILE["libraries"].items():
        settings = dict(
            name = library["name"],
            srcs = [_file(path) for path in library["srcs"]],
            hdrs = [_file(path) for path in library["generated_headers"]],
            copts = library["copts"],
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if not name.startswith("$LLVM_ROOT/")],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = [":source_headers"] + [_label(dep) for dep in library["gn_deps"] if _library_dep(dep)],
        )
        if library["kind"] == "executable":
            settings["srcs"] += settings.pop("hdrs")
            cc_binary(**settings)
        else:
            settings["alwayslink"] = library["kind"] == "source_set"
            if original == "//third_party/jsoncpp:jsoncpp":
                settings["defines"] = [item for item in library["defines"] if item.startswith("JSON_")]
            cc_library(**settings)
    native.alias(name = "perfetto", actual = _label(PROFILE["root"]))
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if library["srcs"] and library["kind"] != "executable"])

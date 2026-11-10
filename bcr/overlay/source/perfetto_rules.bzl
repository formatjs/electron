"""Complete captured Perfetto runtime, native plugins and original generators."""

load("@electron_perfetto_native_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_CPUS = {"x64": "x86_64", "arm64": "aarch64"}

def _compatible(record):
    return ["@platforms//os:linux", "@platforms//cpu:" + _CPUS[record.get("architecture", "x64")]]

def _label(original, profile, external):
    if original in external:
        return external[original]
    return ":" + profile["names"][original]

def _file(original):
    if original.startswith(_BUILD):
        return ":" + original[len(_BUILD):]
    if original.startswith("//third_party/protobuf/"):
        return "@electron_protobuf_sources//:" + original[2:]
    return "//:" + original[2:]

def _library_dep(original, profile):
    if original in profile["toolchain_deps"] or original in profile.get("external_executables", ["//third_party/protobuf:protoc"]):
        return False
    if original in profile["libraries"] and profile["libraries"][original]["kind"] == "executable":
        return False
    return True

def electron_perfetto(profile = PROFILE, external = None):
    """Bind one family profile; cross-family providers require explicit owners."""
    owners = dict(profile["external"])
    for label, owner in (external or {}).items():
        if label not in owners:
            fail("Unknown Perfetto external identity: " + label)
        owners[label] = owner
    for label, owner in owners.items():
        if not owner:
            fail("Missing Perfetto external owner: " + label)
    native.exports_files(profile["files"] + ["profile.bzl", "BUILD.bazel"])
    cc_library(
        name = "source_headers",
        hdrs = profile["headers"],
        includes = [".", "third_party/perfetto", "third_party/perfetto/include", "third_party/jsoncpp/source/include"],
    )
    for original, action in profile["actions"].items():
        outputs = [path[len(_BUILD):] for path in action["outputs"]]
        electron_source_action(
            name = action["name"] + "_run",
            srcs = {_file(path): path[2:] for path in action["inputs"]},
            tools = {_label(tool, profile, owners): logical for logical, tool in action["tools"].items()},
            out_files = outputs,
            logical_outputs = outputs,
            script = action["script"],
            args = action["args"],
            response = action["response"],
            deps = [":" + profile["actions"][dep]["name"] + "_run" for dep in action["gn_deps"] if dep in profile["actions"]],
            target_compatible_with = _compatible(action),
        )
        cc_library(
            name = action["name"],
            hdrs = [":" + path for path in outputs if path.endswith(".h")],
            includes = [root + suffix for root in action.get("generated_include_roots", ["gen"]) for suffix in ["", "/third_party/perfetto", "/third_party/perfetto/build_config"]],
            target_compatible_with = _compatible(action),
        )
    for original, library in profile["libraries"].items():
        settings = dict(
            name = library["name"],
            srcs = [_file(path) for path in library["srcs"]],
            hdrs = [_file(path) for path in library["generated_headers"]],
            copts = library["copts"],
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if not name.startswith("$LLVM_ROOT/")],
            linkstatic = True,
            target_compatible_with = _compatible(library),
            deps = [":source_headers"] + [_label(dep, profile, owners) for dep in library["gn_deps"] if _library_dep(dep, profile)],
        )
        if library["kind"] == "executable":
            settings["srcs"] += settings.pop("hdrs")
            cc_binary(**settings)
        else:
            settings["alwayslink"] = library["kind"] == "source_set"
            if original.split("(")[0] == "//third_party/jsoncpp:jsoncpp":
                settings["defines"] = [item for item in library["defines"] if item.startswith("JSON_")]
            cc_library(**settings)
    native.alias(name = "perfetto", actual = _label(profile["root"], profile, owners))
    native.filegroup(name = "libraries", srcs = [_label(label, profile, owners) for label, library in profile["libraries"].items() if library["srcs"] and library["kind"] != "executable"])

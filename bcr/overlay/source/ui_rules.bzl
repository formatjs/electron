"""Complete native ui/base with original WebUI, lint and TypeScript producers."""

load("@bazel_skylib//rules:expand_template.bzl", "expand_template")
load("@electron_ui_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(profile, original):
    if original.startswith("@"):
        return original
    return profile["external"].get(original, ":" + profile["names"].get(original, ""))

def _file(profile, original):
    if original in profile["external_files"]:
        return profile["external_files"][original]
    if original in profile["generated_files"]:
        return "//:" + original[2:]
    return ":" + original[len(_BUILD):] if original.startswith(_BUILD) else "//:" + original[2:]

def electron_ui(profile = PROFILE, aliases = None, node_modules = ":node_modules"):
    native.exports_files(profile["files"] + [path[2:] for path in profile["generated_files"]] + ["profile.bzl", "BUILD.bazel"])
    cc_library(
        name = "source_headers",
        hdrs = {_file(profile, "//" + path): True for headers in profile["headers"].values() for path in headers}.keys() + [_file(profile, path) for action in profile["actions"].values() for path in action["outputs"] if path.endswith(".h")],
        textual_hdrs = [_file(profile, "//" + path) for path in profile["textual_headers"]],
        includes = [".", "gen", "gen/third_party/perfetto", "gen/third_party/perfetto/build_config"],
        deps = ["@electron_events_sources//:source_headers", "@electron_xcb_sources//:libxcb", "@xkbcommon//:xkbcommon", "@electron_mojo_sources//:bindings", "@electron_partition_alloc_sources//:raw_ptr"],
        target_compatible_with = _COMPATIBLE,
    )
    native.filegroup(name = "node_modules", srcs = [_file(profile, "//" + path) for path in profile["node_modules_files"]])
    adapters = {}
    for source, substitutions in profile.get("source_adapters", {}).items():
        name = "source_adapter_" + source[2:].replace("/", "_").replace(".", "_")
        expand_template(name = name, template = _file(profile, source), substitutions = substitutions, out = "source_adapters/" + source[2:])
        adapters[source] = ":" + name
    for original, action in profile["actions"].items():
        outputs = [path[len(_BUILD):] for path in action["outputs"]]
        electron_source_action(
            name = action["name"] + "_run",
            srcs = {adapters.get(path, _file(profile, path)): path[2:] for path in action["inputs"]},
            tools = {_label(profile, label): path[2:] for path, label in action["tools"].items()},
            source_groups = [node_modules] if action["node_modules"] else [],
            deps = [":" + profile["names"][label] + "_run" for label in action["ordering_deps"]],
            exec_compatible_with = _COMPATIBLE,
            script = action["script"],
            args = action["args"],
            response = action["response"],
            out_files = outputs,
            logical_outputs = outputs,
            target_compatible_with = _COMPATIBLE,
        )
        cc_library(
            name = action["name"],
            hdrs = [_file(profile, path) for path in action["outputs"] if path.endswith(".h")],
            textual_hdrs = [_file(profile, path) for path in action["outputs"] if path.endswith((".inc", ".cc"))],
            data = [_file(profile, path) for path in action["outputs"] if not path.endswith((".h", ".inc", ".cc"))],
            includes = ["gen"],
            target_compatible_with = _COMPATIBLE,
        )
    for original, copy in profile["copies"].items():
        outputs = [path[len(_BUILD):] for path in copy["outputs"]]
        arguments = []
        for source, output in zip(copy["sources"], outputs):
            arguments += ["../../" + source[2:], output]
        inputs = {_file(profile, path): path[2:] for path in copy["sources"]}
        inputs["@electron//electron/private:copy_files.py"] = "electron/private/copy_files.py"
        electron_source_action(name = copy["name"] + "_run", srcs = inputs, script = "electron/private/copy_files.py", args = arguments, out_files = outputs, logical_outputs = outputs, target_compatible_with = _COMPATIBLE)
        cc_library(name = copy["name"], hdrs = [_file(profile, path) for path in copy["outputs"] if path.endswith(".h")], textual_hdrs = [_file(profile, path) for path in copy["outputs"] if path.endswith(".cc")], includes = ["gen"], target_compatible_with = _COMPATIBLE)
    for original, metadata in profile["metadata"].items():
        cc_library(name = metadata["name"], data = [_file(profile, path) for path in metadata["outputs"]], target_compatible_with = _COMPATIBLE)
    for original, library in profile["libraries"].items():
        settings = dict(
            hdrs = {_file(profile, path): True for path in library["source_headers"] + library["public_headers"]}.keys(),
            textual_hdrs = {_file(profile, path): True for path in library["compiler_inputs"]}.keys(),
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if name in ["m", "dl", "rt", "pthread", "resolv"]],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = [":source_headers"] + list({_label(profile, dep): True for dep in library["gn_deps"] if dep not in profile["toolchain_deps"] and dep not in profile["execution_tools"]}),
        )
        if "xcb" in library["libs"]:
            settings["deps"] += ["@electron_xcb_sources//:libxcb"]
        if "xkbcommon" in library["libs"]:
            settings["deps"] += ["@xkbcommon//:xkbcommon"]
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
                cc_library(name = library["name"] + "_" + language, srcs = [_file(profile, path) for path in sources], copts = flags, alwayslink = library["kind"] == "source_set", **settings)
                settings["deps"] += [":" + library["name"] + "_" + language]
        if library["kind"] == "executable":
            settings.pop("includes")
            settings["srcs"] = [_file(profile, path) for path in library["srcs"]] + settings.pop("hdrs") + settings.pop("textual_hdrs")
            cc_binary(name = library["name"], copts = library["copts"], **settings)
        else:
            cc_library(name = library["name"], srcs = [_file(profile, path) for path in library["srcs"]], copts = library["copts"], alwayslink = library["kind"] == "source_set", **settings)
    for name, original in ({"base": "//ui/base:base", "color": "//ui/color:color", "color_mojom": "//ui/color:mojom", "resources": "//ui/webui/resources:resources_grit", "strings": "//ui/strings:ui_strings_grit"} if aliases == None else aliases).items():
        native.alias(name = name, actual = _label(profile, original))
    native.filegroup(name = "libraries", srcs = [_label(profile, label) for label, library in profile["libraries"].items() if library["kind"] != "executable" and (library["srcs"] or library["c_srcs"] or library["asm_srcs"])])

"""Original Ozone, GL, ANGLE, SwiftShader, Vulkan and Wayland native targets."""

load("@electron_platform_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_import.bzl", "cc_import")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(original):
    if original.startswith("@"):
        return original
    return PROFILE["external"].get(original, ":" + PROFILE["names"].get(original, ""))

def _file(original):
    if original in PROFILE["external_files"]:
        return PROFILE["external_files"][original]
    if original in PROFILE["generated_files"]:
        return "//:" + original[2:]
    return ":" + original[len(_BUILD):] if original.startswith(_BUILD) else "//:" + original[2:]

def _system_deps(library):
    libs = library["libs"]
    deps = []
    for names, target in [
        (["glib-2.0", "gmodule-2.0", "gobject-2.0", "gthread-2.0"], "@glib//glib"),
        (["gio-2.0"], "@glib//gio"),
        (["nss3", "nssutil3", "smime3", "nspr4", "plc4", "plds4"], "@nss//:nss"),
        (["expat"], "@libexpat//:libexpat"),
        (["uuid"], "@libuuid//:uuid"),
        (["xcb"], "@electron_xcb_sources//:libxcb"),
        (["xkbcommon"], "@xkbcommon//:xkbcommon"),
        (["pci"], "@electron_platform_pciutils//:pci"),
        (PROFILE["sdk_libraries"], "@electron_platform_sdk//:desktop"),
    ]:
        if any([name in libs for name in names]):
            deps.append(target)
    return deps

def _link_settings(library):
    flags = []
    for flag in library["gn_ldflags"]:
        if flag in ["-Werror", "-nostdlib++"] or flag.startswith(("--target=", "--sysroot=")):
            continue
        if flag.startswith("-Wl,--version-script=../../"):
            flag = "-Wl,--version-script=$(location " + _file("//" + flag[len("-Wl,--version-script=../../"):]) + ")"
        flags.append(flag)
    return dict(linkopts = flags, additional_linker_inputs = [_file(path) for path in library["linker_inputs"]])

def electron_platform():
    native.exports_files(PROFILE["files"] + [path[2:] for path in PROFILE["generated_files"]] + ["profile.bzl", "BUILD.bazel"])
    cc_library(
        name = "tool_headers",
        hdrs = {_file("//" + path): True for headers in PROFILE["headers"].values() for path in headers}.keys(),
        includes = [".", "gen"],
        deps = ["@electron_ui_sources//:source_headers", "@electron_platform_sdk//:headers", "@electron_partition_alloc_sources//:raw_ptr"],
        target_compatible_with = _COMPATIBLE,
    )
    cc_library(
        name = "source_headers",
        hdrs = {_file("//" + path): True for headers in PROFILE["headers"].values() for path in headers}.keys() + [_file(path) for action in PROFILE["actions"].values() for path in action["outputs"] if path.endswith((".h", ".hpp", ".inc", ".inl"))],
        includes = [".", "gen"],
        deps = ["@electron_ui_sources//:source_headers", "@electron_platform_sdk//:headers", "@electron_partition_alloc_sources//:raw_ptr"],
        target_compatible_with = _COMPATIBLE,
    )
    for original, action in PROFILE["actions"].items():
        runs = []
        for index, run in enumerate(action["runs"]):
            name = action["name"] + "_run_" + str(index)
            runs.append(":" + name)
            outputs = [path[len(_BUILD):] for path in run["outputs"]]
            electron_source_action(
                name = name,
                srcs = {_file(path): path[2:] for path in action["inputs"]},
                tools = {_label(label): path[2:] for path, label in action["tools"].items()},
                deps = [":" + PROFILE["names"][label] + "_runs" for label in action["ordering_deps"]],
                exec_compatible_with = _COMPATIBLE,
                script = action["script"],
                args = run["args"],
                response = action["response"],
                environment = action["environment"],
                out_files = outputs,
                logical_outputs = outputs,
                target_compatible_with = _COMPATIBLE,
            )
        native.filegroup(name = action["name"] + "_runs", srcs = runs)
        cc_library(
            name = action["name"],
            hdrs = [_file(path) for path in action["outputs"] if path.endswith((".h", ".hpp", ".inl"))],
            textual_hdrs = [_file(path) for path in action["outputs"] if path.endswith((".inc", ".cc"))],
            data = [_file(path) for path in action["outputs"] if not path.endswith((".h", ".hpp", ".inl", ".inc", ".cc"))],
            includes = ["gen"],
            target_compatible_with = _COMPATIBLE,
        )
    for original, metadata in PROFILE["metadata"].items():
        cc_library(name = metadata["name"], data = [_file(path) for path in metadata["outputs"]], target_compatible_with = _COMPATIBLE)
    shared = []
    for original, library in PROFILE["libraries"].items():
        settings = dict(
            hdrs = {_file(path): True for path in library["source_headers"] + library["public_headers"]}.keys(),
            textual_hdrs = {_file(path): True for path in library["compiler_inputs"]}.keys(),
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if name in ["m", "dl", "rt", "pthread", "resolv"]],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = [":tool_headers" if original in PROFILE["execution_closure"] else ":source_headers"] + _system_deps(library) + list({_label(dep): True for dep in library["gn_deps"] if dep not in PROFILE["toolchain_deps"] and dep not in PROFILE["execution_tools"]}),
        )
        for language, sources, flags in [("c", library["c_srcs"], library["c_copts"]), ("asm", library["asm_srcs"], library["asm_copts"])]:
            if sources:
                cc_library(name = library["name"] + "_" + language, srcs = [_file(path) for path in sources], copts = flags, alwayslink = library["kind"] == "source_set", **settings)
                settings["deps"] += [":" + library["name"] + "_" + language]
        if library["kind"] == "executable":
            settings.pop("includes")
            settings["srcs"] = [_file(path) for path in library["srcs"]] + settings.pop("hdrs") + settings.pop("textual_hdrs")
            link = _link_settings(library)
            settings["linkopts"] += link.pop("linkopts")
            cc_binary(name = library["name"], copts = library["copts"], **dict(settings, **link))
        elif library["kind"] == "shared_library":
            internal = library["name"] + "_objects"
            cc_library(name = internal, srcs = [_file(path) for path in library["srcs"]], copts = library["copts"], alwayslink = True, **settings)
            soname = library["outputs"][0].split("/")[-1]
            shared.append(":" + soname)
            link = _link_settings(library)
            link["linkopts"] += ["-Wl,-soname," + soname]
            cc_binary(name = soname, deps = [":" + internal], linkshared = True, linkstatic = True, target_compatible_with = _COMPATIBLE, **link)
            cc_import(name = library["name"] + "_import", shared_library = ":" + soname, target_compatible_with = _COMPATIBLE)
            cc_library(name = library["name"], deps = [":" + library["name"] + "_import", ":source_headers"], target_compatible_with = _COMPATIBLE)
        else:
            cc_library(name = library["name"], srcs = [_file(path) for path in library["srcs"]], copts = library["copts"], alwayslink = library["kind"] == "source_set", **settings)
    icds = [_file(path) for action in PROFILE["actions"].values() if action["script"] in ["third_party/swiftshader/src/Vulkan/write_icd_json.py", "third_party/vulkan-tools/src/scripts/gn/generate_vulkan_icd_json.py"] for path in action["outputs"]]
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if library["kind"] != "executable"] + shared + icds)
    native.filegroup(name = "runtime", srcs = shared + icds + ["@electron_platform_runtime//:libraries", "@electron_platform_pciutils//:libpci.so.3"])
    native.alias(name = "ozone", actual = _label("//ui/ozone:ozone"))
    native.alias(name = "gl", actual = _label("//ui/gl:gl"))

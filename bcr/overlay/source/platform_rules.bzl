"""Original Ozone, GPU, media, compositor and graphics native targets."""

load("@electron_platform_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_import.bzl", "cc_import")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")
load("//electron:source_headers.bzl", "electron_source_headers")
load("//electron:source_tool.bzl", "electron_source_tool")

_BUILD = "//out/bazel-import/"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(original):
    if original.startswith("@"):
        return original
    return PROFILE["external"].get(original, ":" + PROFILE["names"].get(original, ""))

def _file(original):
    original = PROFILE.get("source_aliases", {}).get(original, original)
    if original in PROFILE["external_files"]:
        return PROFILE["external_files"][original]
    if original in PROFILE["generated_files"]:
        return "//:" + original[2:]
    return ":" + original[len(_BUILD):] if original.startswith(_BUILD) else "//:" + original[2:]

def _system_deps(original, library):
    libs = library["libs"]
    deps = []
    for names, target in [
        (["glib-2.0", "gmodule-2.0", "gobject-2.0", "gthread-2.0"], "@glib//glib"),
        (["gio-2.0"], "@glib//gio"),
        (["z"], "@electron_v8_support_sources//:zlib"),
        (["nss3", "nssutil3", "smime3", "nspr4", "plc4", "plds4"], "@nss//:nss"),
        (["expat"], "@libexpat//:libexpat"),
        (["uuid"], "@libuuid//:uuid"),
        (["xcb"], "@electron_xcb_sources//:libxcb"),
        (["xkbcommon"], "@xkbcommon//:xkbcommon"),
        (["pci"], "@electron_platform_pciutils//:pci"),
    ]:
        if any([name in libs for name in names]):
            deps.append(target)
    deps += ["@electron_platform_sdk//:" + name for name in library["libs"] if name in PROFILE["sdk_libraries"] and name != "pci"]
    if original in ["//media/gpu/vaapi:libva_stubs", "//media/gpu/chromeos:fourcc"]:
        deps.append("@electron_platform_sdk//:va_headers")
    return deps

def _link_settings(library):
    flags = []
    for flag in library["gn_ldflags"]:
        if flag in library.get("replaced_rust_toolchain_flags", []):
            continue
        if flag in ["-Werror", "-nostdlib++"] or flag.startswith(("--target=", "--sysroot=")):
            continue
        if flag.startswith("-Wl,--version-script=../../"):
            flag = "-Wl,--version-script=$(location " + _file("//" + flag[len("-Wl,--version-script=../../"):]) + ")"
        flags.append(flag)
    return dict(linkopts = flags, additional_linker_inputs = [_file(path) for path in library["linker_inputs"]])

def electron_platform():
    native.exports_files(PROFILE["files"] + [path[2:] for path in PROFILE["generated_files"]] + ["profile.bzl", "BUILD.bazel", "native_compat_patches.json"])
    layers = PROFILE.get("header_layers")
    platform_actions = PROFILE.get("native_header_actions", PROFILE["actions"].keys())
    core_libraries = {}
    module_libraries = {}
    if layers:
        common_headers = [_file("//" + path) for path in layers["platform"]["headers"]]
        platform_actions = layers["platform"]["actions"]
        core_libraries = {label: True for label in layers["blink_core"]["libraries"]}
        module_libraries = {label: True for label in layers.get("blink_modules", {}).get("libraries", [])}
    else:
        common_headers = {_file("//" + path): True for directory, headers in PROFILE["headers"].items() for path in headers if directory != "third_party/wayland/include"}.keys()
    electron_source_headers(
        name = "upstream_headers",
        deps = ["@electron_ui_sources//:source_headers", "@electron_partition_alloc_sources//:raw_ptr"],
    )
    cc_library(
        name = "tool_headers",
        hdrs = common_headers,
        includes = [".", "gen", "src"],
        deps = [":upstream_headers", "@electron_platform_sdk//:headers"],
        target_compatible_with = _COMPATIBLE,
    )
    cc_library(
        name = "source_headers",
        hdrs = common_headers + [_file(path) for label in platform_actions for path in PROFILE["actions"][label]["outputs"] if path.endswith((".h", ".hpp", ".inc", ".inl"))],
        includes = [".", "gen", "src"],
        deps = [":upstream_headers", "@electron_platform_sdk//:headers"],
        target_compatible_with = _COMPATIBLE,
    )
    if layers:
        cc_library(
            name = "core_source_headers",
            hdrs = [_file("//" + path) for path in layers["blink_core"]["headers"]] + [_file(path) for label in layers["blink_core"]["actions"] for path in PROFILE["actions"][label]["outputs"] if path.endswith((".h", ".hpp", ".inc", ".inl"))],
            includes = [".", "gen", "src"],
            deps = [":source_headers"],
            target_compatible_with = _COMPATIBLE,
        )
    if layers and "blink_modules" in layers:
        cc_library(
            name = "modules_source_headers",
            hdrs = [_file("//" + path) for path in layers["blink_modules"]["headers"]] + [_file(path) for label in layers["blink_modules"]["actions"] for path in PROFILE["actions"][label]["outputs"] if path.endswith((".h", ".hpp", ".inc", ".inl"))],
            includes = [".", "gen", "src"],
            deps = [":core_source_headers"],
            target_compatible_with = _COMPATIBLE,
        )
    native.filegroup(name = "devtools_node_modules", srcs = PROFILE.get("devtools_node_modules_files", []))
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
                source_groups = [":devtools_node_modules"] if action.get("devtools_node_modules") else [],
                tool_inputs = [":" + PROFILE["libraries"][label]["name"] + "_runtime" for label in action["tools"].values() if PROFILE["libraries"].get(label, {}).get("native_tool_data")],
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
    for original, copy in PROFILE.get("copies", {}).items():
        outputs = [path[len(_BUILD):] for path in copy["outputs"]]
        arguments = []
        for source, output in zip(copy["sources"], outputs):
            arguments += ["../../" + source[2:], output]
        inputs = {_file(path): path[2:] for path in copy["sources"]}
        inputs["@electron//electron/private:copy_files.py"] = "electron/private/copy_files.py"
        electron_source_action(name = copy["name"] + "_run", srcs = inputs, script = "electron/private/copy_files.py", args = arguments, out_files = outputs, logical_outputs = outputs, target_compatible_with = _COMPATIBLE)
        cc_library(name = copy["name"], hdrs = [_file(path) for path in copy["outputs"] if path.endswith(".h")], textual_hdrs = [_file(path) for path in copy["outputs"] if not path.endswith(".h")], includes = ["gen"], target_compatible_with = _COMPATIBLE)
    for original, metadata in PROFILE["metadata"].items():
        cc_library(name = metadata["name"], data = [_file(path) for path in metadata["outputs"]], target_compatible_with = _COMPATIBLE)
    shared = []
    for original, library in PROFILE["libraries"].items():
        settings = dict(
            hdrs = {_file(path): True for path in library["source_headers"] + library["public_headers"]}.keys() + ([_file("//" + path) for path in PROFILE["headers"]["third_party/wayland/include"]] if original.startswith("//third_party/wayland:") else []),
            textual_hdrs = {_file(path): True for path in library["compiler_inputs"] + library.get("textual_headers", [])}.keys(),
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if name in ["m", "dl", "rt", "pthread", "resolv"]],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = {dep: True for dep in [":tool_headers" if original in PROFILE["execution_closure"] else (":modules_source_headers" if original in module_libraries else ":core_source_headers" if original in core_libraries else ":source_headers")] + _system_deps(original, library) + [_label(dep) for dep in library["gn_deps"] if dep not in PROFILE["toolchain_deps"] and dep not in PROFILE["execution_tools"]]}.keys(),
        )
        if library.get("resource_sources"):
            settings["data"] = [_file(path) for path in library["resource_sources"]]
        for language, sources, flags in [("c", library["c_srcs"], library["c_copts"]), ("asm", library["asm_srcs"], library["asm_copts"])]:
            if sources:
                compiler_inputs = []
                if language == "c":
                    for header in library.get("native_configuration_headers", []):
                        compiler_inputs.append(_file(header))
                        flags = flags + ["-include", "$(location " + _file(header) + ")"]
                cc_library(name = library["name"] + "_" + language, srcs = [_file(path) for path in sources], copts = flags, additional_compiler_inputs = compiler_inputs, alwayslink = library["kind"] in ["source_set", "shared_library"], **settings)
                settings["deps"] += [":" + library["name"] + "_" + language]
        if library["kind"] == "executable":
            settings.pop("includes")
            settings["srcs"] = [_file(path) for path in library["srcs"]] + settings.pop("hdrs") + settings.pop("textual_hdrs")
            link = _link_settings(library)
            settings["linkopts"] += link.pop("linkopts")
            cc_binary(name = library["name"], copts = library["copts"], **dict(settings, **link))
            if library.get("native_tool_data"):
                electron_source_tool(name = library["name"] + "_runtime", binary = ":" + library["name"], data = library["native_tool_data"], target_compatible_with = _COMPATIBLE)
        elif library["kind"] == "shared_library":
            internal = library["name"] + "_objects"
            cc_library(name = internal, srcs = [_file(path) for path in library["srcs"]], copts = library["copts"], alwayslink = True, **settings)
            soname = library["outputs"][0].split("/")[-1]
            shared.append(":" + soname)
            link = _link_settings(library)
            link["linkopts"] += ["-Wl,-soname," + soname]
            link["dynamic_deps"] = ["@electron//source/glib:" + name for name in ["zlib", "glib", "gobject", "gmodule", "gio"]]
            cc_binary(name = soname, deps = [":" + internal], linkshared = True, linkstatic = True, target_compatible_with = _COMPATIBLE, **link)
            cc_import(name = library["name"] + "_import", shared_library = ":" + soname, target_compatible_with = _COMPATIBLE)
            cc_library(name = library["name"], deps = [":" + library["name"] + "_import", ":source_headers"], target_compatible_with = _COMPATIBLE)
        else:
            cc_library(name = library["name"], srcs = [_file(path) for path in library["srcs"]], copts = library["copts"], alwayslink = library["kind"] == "source_set", **settings)
    icds = [_file(path) for action in PROFILE["actions"].values() if action["script"] in ["third_party/swiftshader/src/Vulkan/write_icd_json.py", "third_party/vulkan-tools/src/scripts/gn/generate_vulkan_icd_json.py"] for path in action["outputs"]]
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if library["kind"] != "executable"] + shared + icds)
    native.filegroup(name = "devtools_frontend", srcs = [":" + PROFILE["actions"][label]["name"] + "_runs" for label in PROFILE.get("devtools_frontend_actions", [])])
    native.filegroup(name = "blink_bindings", srcs = [":" + PROFILE["actions"][label]["name"] + "_runs" for label in PROFILE["roots"] if label.startswith("//third_party/blink/") and label in PROFILE["actions"]])
    native.filegroup(name = "runtime", srcs = ["@electron//source/glib:runtime"] + shared + icds + ["@electron_platform_runtime//:libraries", "@electron_platform_pciutils//:libpci.so.3"])
    native.alias(name = "blink_platform", actual = _label("//third_party/blink/renderer/platform:platform"))
    if "//third_party/blink/renderer/core:core" in PROFILE["libraries"]:
        native.alias(name = "blink_core", actual = _label("//third_party/blink/renderer/core:core"))
    if "//third_party/blink/renderer/modules:modules" in PROFILE["libraries"]:
        native.alias(name = "blink_modules", actual = _label("//third_party/blink/renderer/modules:modules"))
    native.alias(name = "ozone", actual = _label("//ui/ozone:ozone"))
    native.alias(name = "gl", actual = _label("//ui/gl:gl"))

    for name, original in {"compositor": "//cc:cc", "media": "//media:media", "ffmpeg": "//third_party/ffmpeg:ffmpeg", "gpu_client": "//gpu/command_buffer/client:gles2_implementation", "gpu_service": "//gpu/command_buffer/service:gles2", "viz_common": "//components/viz/common:common"}.items():
        native.alias(name = name, actual = _label(original))

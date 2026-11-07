"""Complete captured Mojo embedder/network closure and original generators."""

load("@electron_network_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_import.bzl", "cc_import")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _label(original):
    return PROFILE["external"].get(original, ":" + PROFILE["names"].get(original, ""))

def _file(original):
    if original in PROFILE["generated_files"]:
        return "//:" + original[2:]
    return ":" + original[len(_BUILD):] if original.startswith(_BUILD) else "//:" + original[2:]

def _family(original):
    if original == "//mojo/public/cpp/bindings:default_construct_tag":
        return "default_construct_tag_headers"
    path = original[2:].split(":")[0]
    selected = ""
    for family in PROFILE["headers"]:
        if (path == family or path.startswith(family + "/")) and len(family) > len(selected):
            selected = family
    for family in [path + "/src", path + "/src/amalgamation"]:
        if family in PROFILE["headers"]:
            selected = family
    return selected.replace("/", "_") + "_headers" if selected else "common_headers"

def electron_network():
    native.exports_files(PROFILE["files"] + [path[2:] for path in PROFILE["generated_files"]] + ["profile.bzl", "BUILD.bazel", "native_compat_patches.json"])
    cc_import(name = "atomic_runtime", static_library = "@llvm//runtimes/compiler-rt:clang_rt.builtins.static", target_compatible_with = _COMPATIBLE)
    cc_library(name = "common_headers", includes = ["."])
    cc_library(name = "default_construct_tag_headers", hdrs = ["mojo/public/cpp/bindings/default_construct_tag.h"], includes = ["."])
    for family, headers in PROFILE["headers"].items():
        cc_library(name = family.replace("/", "_") + "_headers", hdrs = headers, includes = ["."], deps = [_label(dep) for dep in PROFILE["native_extra_header_deps"].get(family, [])] + [":" + other.replace("/", "_") + "_headers" for other in PROFILE["native_extra_header_families"].get(family, [])])
    for original, action in PROFILE["actions"].items():
        for index, run in enumerate(action["runs"]):
            outputs = [path[len(_BUILD):] for path in run["outputs"]]
            electron_source_action(
                name = action["name"] + "_run_" + str(index),
                srcs = {_file(path): path[2:] for path in run["inputs"] if path not in run["tools"]},
                tools = {label: path[2:] for path, label in run["tools"].items()},
                script = action["script"],
                args = run["args"],
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
            hdrs = {_file(path): True for path in library["generated_headers"] + library["public_headers"]}.keys(),
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if name in ["m", "dl", "rt", "pthread", "resolv"]],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = [":" + _family(original), "@electron_network_platform_headers//:gssapi"] + list({_label(dep): True for dep in library["gn_deps"] if dep not in PROFILE["toolchain_deps"]}),
        )
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
        if library["kind"] == "executable":
            settings.pop("includes")
            settings["srcs"] = [_file(path) for path in library["srcs"]] + settings.pop("hdrs")
            cc_binary(name = library["name"], copts = library["copts"], **settings)
        else:
            cc_library(name = library["name"], srcs = [_file(path) for path in library["srcs"]], copts = library["copts"], alwayslink = library["kind"] == "source_set", **settings)
    for name, original in {"mojo_embedder": PROFILE["root"], "net": "//net:net", "crypto": "//crypto:crypto", "url": "//url:url", "sql": "//sql:sql"}.items():
        native.alias(name = name, actual = _label(original))
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if library["srcs"] or library["c_srcs"] or library["asm_srcs"]])

"""Matching complete Chromium base and original Rust CXX generators."""

load("@electron_base_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")

_BUILD = "//out/bazel-import/"
_CFG = "//build/rust/gni_impl:rustc_print_cfg"
_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _rustc_cfg_impl(ctx):
    rust = ctx.attr._rust[platform_common.ToolchainInfo]
    ctx.actions.run(
        executable = rust.rustc,
        arguments = ["--print=cfg=" + ctx.outputs.out.path, "--target=" + str(rust.target_flag_value)],
        inputs = rust.all_files,
        outputs = [ctx.outputs.out],
        env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronRustcCfg",
    )
    return [DefaultInfo(files = depset([ctx.outputs.out]))]

_rustc_cfg = rule(
    implementation = _rustc_cfg_impl,
    attrs = {
        "out": attr.output(mandatory = True),
        "_rust": attr.label(default = Label("@rules_rust//rust/toolchain:current_rust_toolchain")),
    },
)

def _copy_impl(ctx):
    for source, output in zip(ctx.files.srcs, ctx.outputs.outs):
        ctx.actions.symlink(output = output, target_file = source)
    return [DefaultInfo(files = depset(ctx.outputs.outs))]

_copy = rule(
    implementation = _copy_impl,
    attrs = {"srcs": attr.label_list(allow_files = True), "outs": attr.output_list()},
)

def _label(original):
    return PROFILE["external"].get(original, ":" + PROFILE["names"].get(original, ""))

def _file(original):
    if original in PROFILE["external_files"]:
        return PROFILE["external_files"][original]
    if original.startswith(_BUILD):
        return ":" + original[len(_BUILD):]
    return "//:" + original[2:]

def _library_dep(original):
    if original in PROFILE["toolchain_deps"] or original == "//third_party/protobuf:protoc":
        return False
    if original in PROFILE["external"] and (original.endswith(":protozero_plugin") or "cxxbridge_cmd/" in original):
        return False
    return True

def electron_base():
    native.exports_files(PROFILE["files"] + ["profile.bzl", "BUILD.bazel"])
    cc_library(
        name = "source_headers",
        hdrs = PROFILE["headers"],
        includes = [".", "gen"],
        deps = [
            "@googletest//:gtest_prod",
            "@electron_partition_alloc_sources//:partition_alloc",
            "@electron_protobuf_sources//:abseil",
            "@electron_boringssl_sources//:ssl",
            "@electron_icu_sources//:icu",
            "@electron_v8_support_sources//:zlib",
        ],
    )
    for original, action in PROFILE["actions"].items():
        outputs = [path[len(_BUILD):] for path in action["outputs"]]
        if original == _CFG:
            _rustc_cfg(name = action["name"] + "_run", out = outputs[0], target_compatible_with = _COMPATIBLE)
        else:
            electron_source_action(
                name = action["name"] + "_run",
                srcs = {_file(path): path[2:] for path in action["inputs"]},
                tools = {_label(tool): logical for logical, tool in action["tools"].items()},
                out_files = outputs,
                logical_outputs = outputs,
                script = action["script"],
                args = action["args"],
                response = action["response"],
                target_compatible_with = _COMPATIBLE,
            )
        cc_library(
            name = action["name"],
            hdrs = [":" + path for path in outputs if path.endswith((".h", ".inc"))],
            includes = ["gen"],
            target_compatible_with = _COMPATIBLE,
        )
    for original, copy in PROFILE["copies"].items():
        outputs = [path[len(_BUILD):] for path in copy["outputs"]]
        _copy(name = copy["name"] + "_run", srcs = [_file(path) for path in copy["srcs"]], outs = outputs, target_compatible_with = _COMPATIBLE)
        cc_library(name = copy["name"], hdrs = [":" + path for path in outputs if path.endswith(".h")], includes = ["gen"], target_compatible_with = _COMPATIBLE)
    for original, library in PROFILE["libraries"].items():
        settings = dict(
            hdrs = [_file(path) for path in library["generated_headers"]],
            local_defines = library["defines"],
            includes = library["includes"],
            linkopts = ["-l" + name for name in library["libs"] if name in ["dl", "pthread", "rt"]],
            linkstatic = True,
            target_compatible_with = _COMPATIBLE,
            deps = [":source_headers"] + {_label(dep): True for dep in library["gn_deps"] if _library_dep(dep)}.keys(),
        )
        if "glib-2.0" in library["libs"]:
            settings["deps"] += ["@glib//glib", "@glib//gmodule", "@glib//gobject"]
        for language, sources, flags in [("c", library["c_srcs"], library["c_copts"]), ("asm", library["asm_srcs"], library["asm_copts"])]:
            if sources:
                cc_library(name = library["name"] + "_" + language, srcs = [_file(path) for path in sources], copts = flags, alwayslink = True, **settings)
                settings["deps"] += [":" + library["name"] + "_" + language]
        cc_library(name = library["name"], srcs = [_file(path) for path in library["srcs"]], copts = library["copts"], alwayslink = library["kind"] == "source_set", **settings)
    cc_library(name = "severity_headers", hdrs = ["base/logging/log_severity.h"], deps = [":source_headers", _label("//base:debugging_buildflags")])
    native.alias(name = "base", actual = _label(PROFILE["root"]))
    native.filegroup(name = "libraries", srcs = [_label(label) for label, library in PROFILE["libraries"].items() if library["srcs"] or library["c_srcs"] or library["asm_srcs"]])

"""Captured V8 source libraries and hermetic execution generators."""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//source/native:v8_base_inputs.bzl", "V8_BASE_LIBRARIES")
load("//source/native:v8_bytecode_inputs.bzl", "BYTECODE_GENERATOR")
load("//source/native:v8_regexp_inputs.bzl", "REGEXP_GENERATOR")
load("//source/native:v8_temporal_inputs.bzl", "V8_TEMPORAL_PROVIDER")
load("//source/native:v8_torque_inputs.bzl", "TORQUE_LIBRARIES", "TORQUE_PROFILE_SHA256", "TORQUE_RUN")

_LINUX_AMD64 = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def v8_generator_headers(name):
    """Share the pinned V8 headers across native execution generators."""
    cc_library(
        name = name,
        hdrs = native.glob(["include/**/*.h", "src/**/*.h"]) + native.glob(["src/**/*.inc", "third_party/**/*.h", "testing/**/*.h"], allow_empty = True),
        includes = [".", "include"],
        target_compatible_with = _LINUX_AMD64,
        deps = [":base_headers"],
    )

def v8_torque_compiler(name):
    """Declare the captured execution compiler inside the patched V8 repository."""
    base = name + "_base"
    library = TORQUE_LIBRARIES["torque_base"]
    cc_library(
        name = base,
        srcs = library["srcs"],
        copts = library["copts"],
        local_defines = library["defines"],
        linkstatic = True,
        alwayslink = True,
        target_compatible_with = _LINUX_AMD64,
        deps = [":generator_headers", ":libbase"],
    )
    tool = TORQUE_LIBRARIES["torque"]
    cc_binary(
        name = name,
        srcs = tool["srcs"],
        copts = tool["copts"],
        local_defines = tool["defines"],
        linkstatic = True,
        target_compatible_with = _LINUX_AMD64,
        deps = [":" + base],
    )
    native.exports_files(TORQUE_RUN["sources"])

def v8_bytecode_compiler(name):
    """Build captured interpreter support and handler-list execution tool."""
    main = "src/builtins/generate-bytecodes-builtins-list.cc"
    cc_library(
        name = "bytecode_generator_support",
        srcs = [p for p in BYTECODE_GENERATOR["srcs"] if p != main],
        copts = BYTECODE_GENERATOR["copts"],
        local_defines = BYTECODE_GENERATOR["defines"],
        linkstatic = True,
        alwayslink = True,
        target_compatible_with = _LINUX_AMD64,
        deps = [":generator_headers", ":libbase"],
    )
    cc_binary(
        name = name,
        srcs = [main],
        copts = BYTECODE_GENERATOR["copts"],
        local_defines = BYTECODE_GENERATOR["defines"],
        linkstatic = True,
        target_compatible_with = _LINUX_AMD64,
        deps = [":bytecode_generator_support"],
    )

def v8_regexp_compiler(name):
    """Build the captured Unicode regexp table execution tool."""
    cc_binary(
        name = name,
        srcs = REGEXP_GENERATOR["srcs"],
        copts = REGEXP_GENERATOR["copts"],
        local_defines = REGEXP_GENERATOR["defines"],
        linkstatic = True,
        target_compatible_with = _LINUX_AMD64,
        deps = [":generator_headers", ":libbase", "@electron_icu_sources//:icu"],
    )

def _generator_impl(ctx):
    prefix = ctx.label.name + "/"
    if ctx.attr.output_subdir:
        prefix += _relative(ctx.attr.output_subdir) + "/"
    output = ctx.actions.declare_file(prefix + _relative(ctx.attr.output))
    ctx.actions.run(
        executable = ctx.attr.tool[DefaultInfo].files_to_run,
        arguments = [output.path],
        outputs = [output],
        env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = ctx.attr.mnemonic,
    )
    return [DefaultInfo(files = depset([output]))]

_v8_generator = rule(
    implementation = _generator_impl,
    attrs = {
        "output_subdir": attr.string(),
        "output": attr.string(mandatory = True),
        "tool": attr.label(executable = True, cfg = "exec", mandatory = True),
        "mnemonic": attr.string(mandatory = True),
    },
)

def electron_v8_bytecodes(name, **kwargs):
    """Generate the captured bytecode handler header."""
    _v8_generator(
        name = name,
        tool = Label("@electron_v8_sources//:bytecode_builtins_list_generator"),
        output = BYTECODE_GENERATOR["output"],
        mnemonic = "ElectronV8Bytecodes",
        **kwargs
    )

def electron_v8_regexp(name, **kwargs):
    """Generate the captured Unicode regexp tables."""
    _v8_generator(
        name = name,
        tool = Label("@electron_v8_sources//:gen-regexp-special-case"),
        output = REGEXP_GENERATOR["output"],
        mnemonic = "ElectronV8RegExp",
        **kwargs
    )

def _relative(path):
    if not path or path.startswith("/") or "\\" in path or ":" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
        fail("Expected canonical relative V8 path: " + path)
    return path

def _torque_impl(ctx):
    inputs = {}
    files = []
    for target, path in ctx.attr.srcs.items():
        _relative(path)
        values = target.files.to_list()
        if len(values) != 1 or path in inputs or not path.endswith(".tq"):
            fail("Torque inputs require one unique .tq file per path")
        inputs[path] = values[0].path
        files.append(values[0])
    if not inputs or sorted(ctx.attr.source_order) != sorted(inputs.keys()):
        fail("Torque source order must cover every declared input exactly once")
    outputs = {}
    if not ctx.attr.out_files:
        fail("Torque requires declared outputs")
    for path in ctx.attr.out_files:
        _relative(path)
        if path in outputs or not path.startswith("torque-generated/") or not any([path.endswith(suffix) for suffix in [".h", ".inc", ".cc"]]):
            fail("Invalid Torque output: " + path)
        outputs[path] = ctx.actions.declare_file(ctx.label.name + "/" + path)
    report = ctx.actions.declare_file(ctx.label.name + "/manifest.json")
    manifest = ctx.actions.declare_file(ctx.label.name + ".inputs.json")
    ctx.actions.write(manifest, json.encode({
        "inputs": inputs,
        "sources": ctx.attr.source_order,
        "outputs": {path: file.path for path, file in outputs.items()},
        "tool": ctx.executable._tool.path,
        "report": report.path,
        "profile_sha256": ctx.attr.profile_sha256,
        "verify_reproducible": ctx.attr.verify_reproducible,
    }))
    ctx.actions.run(
        executable = ctx.executable._runner,
        arguments = [manifest.path],
        inputs = files + [manifest],
        tools = [ctx.attr._tool[DefaultInfo].files_to_run],
        outputs = outputs.values() + [report],
        env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronV8Torque",
    )
    return [
        DefaultInfo(files = depset(outputs.values() + [report])),
        OutputGroupInfo(
            headers = depset([file for path, file in outputs.items() if not path.endswith(".cc")]),
            sources = depset([file for path, file in outputs.items() if path.endswith(".cc")]),
            manifest = depset([report]),
        ),
    ]

electron_v8_torque = rule(
    implementation = _torque_impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = [".tq"], mandatory = True),
        "source_order": attr.string_list(mandatory = True),
        "out_files": attr.string_list(mandatory = True),
        "profile_sha256": attr.string(default = TORQUE_PROFILE_SHA256),
        "verify_reproducible": attr.bool(default = False),
        "_tool": attr.label(default = Label("@electron_v8_sources//:torque"), executable = True, cfg = "exec"),
        "_runner": attr.label(default = Label("//electron/private:torque"), executable = True, cfg = "exec"),
    },
)

def _tool_impl(ctx):
    info = ctx.attr._tool[DefaultInfo]
    return [DefaultInfo(files = info.files, runfiles = ctx.runfiles().merge(info.default_runfiles).merge(info.data_runfiles))]

electron_v8_torque_tool = rule(
    implementation = _tool_impl,
    attrs = {"_tool": attr.label(default = Label("@electron_v8_sources//:torque"), executable = True, cfg = "exec")},
)

def v8_sources():
    """Declare source targets behind the stable repository BUILD shim."""
    native.exports_files(["electron_patches.json", "DEPS", "LICENSE"])
    native.filegroup(name = "sources", srcs = native.glob(["**"], exclude = ["BUILD.bazel"]))

    v8_generator_headers(name = "generator_headers")
    v8_torque_compiler(name = "torque")
    v8_bytecode_compiler(name = "bytecode_builtins_list_generator")
    v8_regexp_compiler(name = "gen-regexp-special-case")

    cc_library(
        name = "temporal_provider",
        srcs = V8_TEMPORAL_PROVIDER["srcs"],
        copts = V8_TEMPORAL_PROVIDER["copts"],
        local_defines = V8_TEMPORAL_PROVIDER["defines"],
        linkstatic = True,
        target_compatible_with = _LINUX_AMD64,
        deps = [":generator_headers", ":libbase", "@electron_icu_sources//:icu", "@electron_rust_sources//:temporal_capi"],
    )

    cc_library(
        name = "base_headers",
        hdrs = native.glob(["include/**/*.h", "src/base/**/*.h", "src/libplatform/**/*.h", "third_party/glibc/**/*.h", "testing/**/*.h"]),
        includes = [".", "include"],
        defines = V8_BASE_LIBRARIES["v8_libbase"]["defines"],
        deps = ["@electron_abseil_sources//absl/synchronization", "@googletest//:gtest_prod"],
    )

    cc_library(
        name = "libm",
        linkstatic = True,
        srcs = V8_BASE_LIBRARIES["libm"]["srcs"],
        copts = V8_BASE_LIBRARIES["libm"]["copts"],
        deps = [":base_headers"],
        target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
    )

    cc_library(
        name = "libbase",
        linkstatic = True,
        srcs = V8_BASE_LIBRARIES["v8_libbase"]["srcs"],
        copts = V8_BASE_LIBRARIES["v8_libbase"]["copts"],
        deps = [":base_headers", ":libm"],
        linkopts = ["-pthread", "-ldl", "-lrt"],
        target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
    )

    cc_library(
        name = "platform_tasks",
        linkstatic = True,
        srcs = V8_BASE_LIBRARIES["v8_libplatform"]["srcs"],
        copts = V8_BASE_LIBRARIES["v8_libplatform"]["copts"],
        deps = [":libbase"],
        target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
    )

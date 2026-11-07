"""Captured V8 Torque compiler and hermetic generation action."""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//source/native:v8_torque_inputs.bzl", "TORQUE_LIBRARIES", "TORQUE_PROFILE_SHA256", "TORQUE_RUN")

def v8_torque_compiler(name):
    """Declare the captured execution compiler inside the patched V8 repository."""
    headers = name + "_headers"
    base = name + "_base"
    compatible = ["@platforms//os:linux", "@platforms//cpu:x86_64"]
    cc_library(
        name = headers,
        hdrs = native.glob(["include/**/*.h", "src/**/*.h"]) + native.glob(["src/**/*.inc", "third_party/**/*.h", "testing/**/*.h"], allow_empty = True),
        includes = [".", "include"],
        target_compatible_with = compatible,
        deps = [":base_headers"],
    )
    library = TORQUE_LIBRARIES["torque_base"]
    cc_library(
        name = base,
        srcs = library["srcs"],
        copts = library["copts"],
        local_defines = library["defines"],
        linkstatic = True,
        alwayslink = True,
        target_compatible_with = compatible,
        deps = [":" + headers, ":libbase"],
    )
    tool = TORQUE_LIBRARIES["torque"]
    cc_binary(
        name = name,
        srcs = tool["srcs"],
        copts = tool["copts"],
        local_defines = tool["defines"],
        linkstatic = True,
        target_compatible_with = compatible,
        deps = [":" + base],
    )
    native.exports_files(TORQUE_RUN["sources"])

def _relative(path):
    if not path or path.startswith("/") or "\\" in path or ":" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
        fail("Expected canonical relative Torque path: " + path)
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

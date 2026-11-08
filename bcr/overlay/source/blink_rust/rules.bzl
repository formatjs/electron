"""Original Blink CXX generators with separate header and link owners."""

load("@electron_rust_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//electron:source_action.bzl", "electron_source_action")
load("//electron:source_headers.bzl", "electron_source_headers")

_COMPATIBLE = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def blink_rust_bridges():
    for name, bridge in PROFILE["blink_bridges"].items():
        electron_source_action(
            name = name + "_generate",
            srcs = dict([("@electron_rust_sources//:" + path, path) for path in bridge["python_inputs"] + [bridge["source"]]] + [(
                "@electron_base_sources//:gen/build/rust/gni_impl/rustc-print-cfg-x86_64-unknown-linux-gnu.txt",
                "out/bazel-import/gen/build/rust/gni_impl/rustc-print-cfg-x86_64-unknown-linux-gnu.txt",
            )]),
            args = bridge["args"],
            logical_outputs = bridge["outputs"],
            out_files = bridge["outputs"],
            script = bridge["script"],
            tools = {"@electron_rust_sources//:cxxbridge": "out/bazel-import/clang_x64_for_rust_host_build_tools/cxxbridge"},
            target_compatible_with = _COMPATIBLE,
        )
        cc_library(
            name = name + "_header_files",
            hdrs = [bridge["outputs"][0]],
            includes = ["gen"],
            deps = [bridge["cppdeps"], "@electron_rust_sources//:blink_headers"],
            target_compatible_with = _COMPATIBLE,
        )
        electron_source_headers(name = name + "_headers", deps = [":" + name + "_header_files"])
        cc_library(
            name = name + "_bridge",
            srcs = [bridge["outputs"][1]],
            copts = bridge["copts"],
            local_defines = bridge["defines"],
            deps = [":" + name + "_header_files"] + ["@electron_rust_sources//:" + dep for dep in bridge["extra_rust_deps"]],
            target_compatible_with = _COMPATIBLE,
        )
        cc_library(
            name = name,
            deps = [":" + name + "_bridge", "@electron_rust_sources//:" + bridge["crate"]],
            target_compatible_with = _COMPATIBLE,
        )
        if bridge.get("helper"):
            helper = bridge["helper"]
            cc_library(
                name = name + "_cpp",
                srcs = ["@electron_rust_sources//:" + path[2:] for path in helper["srcs"]],
                hdrs = ["@electron_rust_sources//:" + path[2:] for path in helper["source_headers"]],
                copts = helper["copts"],
                local_defines = helper["defines"],
                alwayslink = helper["kind"] == "source_set",
                deps = [":" + name],
                target_compatible_with = _COMPATIBLE,
            )

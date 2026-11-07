"""Matching source-built Protobuf runtime, protoc and plugins."""

load("@electron_protobuf_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")

def electron_protobuf():
    native.exports_files(PROFILE["files"] + ["BUILD.bazel", "profile.bzl"])
    cc_library(
        name = "headers",
        hdrs = [path for path in PROFILE["files"] if path.endswith(".h") or path.endswith(".inc")],
        includes = [".", "third_party/protobuf/src", "third_party/protobuf/third_party/utf8_range", "third_party/protobuf-javascript/src"],
    )

    # Public base already carries this private native dependency.
    cc_library(name = "abseil", deps = [dep for dep in PROFILE["abseil_deps"] if dep != "@electron_abseil_sources//absl/base:raw_logging_internal"])
    for label, library in PROFILE["libraries"].items():
        settings = dict(
            name = library["name"],
            srcs = library["srcs"],
            copts = library["copts"],
            local_defines = library["defines"],
            linkstatic = True,
            target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
            deps = [":headers"] + [":" + PROFILE["libraries"][dep]["name"] for dep in library["deps"] if PROFILE["libraries"][dep]["kind"] != "executable"] + ([":abseil"] if library["abseil"] else []),
        )
        if library["kind"] == "executable":
            settings["data"] = [":" + PROFILE["libraries"][dep]["name"] for dep in library["deps"] if PROFILE["libraries"][dep]["kind"] == "executable"]
            cc_binary(**settings)
        else:
            settings["alwayslink"] = library["kind"] == "source_set"
            settings["defines"] = [] if library["name"] == "utf8_range" else ["GOOGLE_PROTOBUF_NO_RTTI", "PROTOBUF_INTERNAL_BOUNDS_CHECK_MODE_ABORT"]
            cc_library(**settings)
    native.filegroup(name = "libraries", srcs = [":protobuf_full", ":protobuf_lite", ":protoc"])

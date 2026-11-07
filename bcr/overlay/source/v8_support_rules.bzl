"""Captured V8 number conversion, SIMD and compression libraries."""

load("@electron_v8_support_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_library.bzl", "cc_library")

def electron_v8_support():
    native.exports_files(PROFILE["files"] + ["profile.bzl", "BUILD.bazel"])
    cc_library(name = "build_headers", hdrs = ["build/build_config.h", "build/buildflag.h"], includes = ["."])
    for family, headers in PROFILE["headers"].items():
        cc_library(name = family + "_all_headers", hdrs = headers, includes = ["."])
    for name, library in PROFILE["libraries"].items():
        cc_library(
            name = name,
            srcs = library["srcs"],
            copts = library["copts"],
            local_defines = library["defines"],
            includes = library["includes"] + (["third_party/zlib"] if library["family"] == "zlib" else []) + (["third_party/zlib/google"] if name == "compression_utils_portable" else []),
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
            deps = [":build_headers", ":" + library["family"] + "_all_headers"] + [":" + dep for dep in library["deps"]],
        )
    native.filegroup(name = "libraries", srcs = [":" + name for name, library in PROFILE["libraries"].items() if library["srcs"]])

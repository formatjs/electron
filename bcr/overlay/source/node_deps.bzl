"""Native Node dependency libraries from the captured Linux AMD64 profile."""

load("@electron//source/native:node_deps_inputs.bzl", "NODE_DEPENDENCIES")
load("@rules_cc//cc:cc_library.bzl", "cc_library")

def node_dependency_libraries(name):
    """Declare pinned libraries in the Node source repository, grouped by name."""
    for library, inputs in NODE_DEPENDENCIES.items():
        cc_library(
            name = name + "_" + library,
            srcs = inputs["srcs"],
            hdrs = native.glob(["deps/" + library + "/**/*.h"]) + native.glob(["deps/" + library + "/**/*." + extension for extension in ["hpp", "inc"]], allow_empty = True),
            copts = inputs["copts"],
            includes = inputs["includes"],
            local_defines = inputs["defines"],
            linkstatic = True,
            target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
            deps = inputs["deps"],
        )
    native.filegroup(
        name = name,
        srcs = [":" + name + "_" + library for library in NODE_DEPENDENCIES],
        target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
    )

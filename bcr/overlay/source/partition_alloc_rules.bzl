"""Captured PartitionAlloc libraries and declared upstream buildflag generation."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//source/native:partition_alloc_inputs.bzl", "PARTITION_ALLOC_BUILDFLAGS", "PARTITION_ALLOC_HEADERS", "PARTITION_ALLOC_LIBRARIES")

def _buildflags_impl(ctx):
    path = PARTITION_ALLOC_BUILDFLAGS["output"]
    output = ctx.actions.declare_file(ctx.label.name + "/" + path)
    response = ctx.actions.declare_file(ctx.label.name + ".rsp")
    ctx.actions.write(response, " ".join(PARTITION_ALLOC_BUILDFLAGS["response"]))
    ctx.actions.run(
        executable = ctx.attr._runner[DefaultInfo].files_to_run,
        arguments = [ctx.file._script.path, "--output", path, "--rulename", PARTITION_ALLOC_BUILDFLAGS["rule"], "--gen-dir", output.path[:-len(path) - 1], "--definitions", response.path],
        inputs = [ctx.file._script, response],
        outputs = [output],
        env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronPartitionAllocBuildflags",
    )
    return [DefaultInfo(files = depset([output]))]

_buildflags = rule(
    implementation = _buildflags_impl,
    attrs = {
        "_script": attr.label(default = Label("@electron_partition_alloc_sources//:src/partition_alloc/write_buildflag_header.py"), allow_single_file = True),
        "_runner": attr.label(default = Label("//electron/private:run_source"), executable = True, cfg = "exec"),
    },
)

def electron_partition_alloc():
    compatible = ["@platforms//os:linux", "@platforms//cpu:x86_64"]
    _buildflags(name = "buildflags")
    cc_library(
        name = "headers",
        hdrs = sorted({p: True for p in PARTITION_ALLOC_HEADERS + [p for name, lib in PARTITION_ALLOC_LIBRARIES.items() if name != "raw_ptr" for p in lib["hdrs"]]}.keys()),
        includes = ["src"],
        target_compatible_with = compatible,
    )
    cc_library(
        name = "buildflags_headers",
        hdrs = [":buildflags"],
        strip_include_prefix = "buildflags/base/allocator/partition_allocator/src",
        target_compatible_with = compatible,
        deps = [":headers"],
    )
    for name in ["allocator_base", "allocator_core", "allocator_shim"]:
        library = PARTITION_ALLOC_LIBRARIES[name]
        cc_library(
            name = name,
            srcs = library["srcs"],
            copts = library["copts"],
            local_defines = library["defines"],
            linkstatic = True,
            linkopts = ["-pthread", "-ldl", "-lrt"],
            target_compatible_with = compatible,
            deps = [":headers", ":buildflags_headers"] + ([":allocator_base"] if name != "allocator_base" else []) + ([":allocator_core"] if name == "allocator_shim" else []),
        )
    cc_library(name = "partition_alloc", deps = [":allocator_shim"], target_compatible_with = compatible)
    raw_ptr = PARTITION_ALLOC_LIBRARIES["raw_ptr"]
    cc_library(
        name = "raw_ptr_headers",
        hdrs = raw_ptr["public_headers"],
        includes = ["src"],
        deps = [":headers", ":buildflags_headers"],
        target_compatible_with = compatible,
    )
    cc_library(
        name = "raw_ptr",
        srcs = raw_ptr["srcs"],
        hdrs = raw_ptr["hdrs"],
        copts = raw_ptr["copts"],
        local_defines = raw_ptr["defines"],
        linkstatic = True,
        target_compatible_with = compatible,
        deps = [":raw_ptr_headers", ":partition_alloc"],
    )
    native.filegroup(name = "libraries", srcs = [":" + name for name in PARTITION_ALLOC_LIBRARIES])
    native.exports_files(["src/partition_alloc/write_buildflag_header.py"])

"""Electron's captured ICU implementation and public file-backed data contract."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("//source/native:icu_inputs.bzl", "ICU_LIBRARIES", "ICU_PUBLIC")

def electron_icu_libraries():
    compatible = ["@platforms//os:linux", "@platforms//cpu:x86_64"]
    cc_library(
        name = "headers",
        hdrs = sorted({p: True for p in ICU_PUBLIC["hdrs"] + ICU_PUBLIC["supplemental_headers"] + [p for lib in ICU_LIBRARIES.values() for p in lib["hdrs"]]}.keys()),
        includes = ["source/common", "source/i18n"],
        defines = ICU_PUBLIC["defines"],
        target_compatible_with = compatible,
    )
    for name in ["icuuc_private", "icui18n"]:
        library = ICU_LIBRARIES[name]
        cc_library(
            name = name,
            srcs = library["srcs"],
            copts = library["copts"],
            local_defines = library["defines"],
            linkstatic = True,
            linkopts = ["-pthread"],
            target_compatible_with = compatible,
            deps = [":headers"] + ([":icuuc_private"] if name == "icui18n" else []),
        )
    cc_library(
        name = "icu",
        target_compatible_with = compatible,
        deps = [":icui18n"],
    )
    native.exports_files([ICU_PUBLIC["data"], "source_provenance.json", "LICENSE"])

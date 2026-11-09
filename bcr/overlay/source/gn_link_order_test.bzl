"""Duplicate archive-member and source-set initializer regression fixtures."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_cc//cc:cc_test.bzl", "cc_test")
load(":gn_link.bzl", "gn_executable_link_context")

def gn_link_order_tests():
    for mode, flags in [("plain", []), ("thin_lto", ["-flto=thin"])]:
        compatible = ["@platforms//os:linux", "@platforms//cpu:x86_64"]
        cc_library(
            name = "gn_lazy_" + mode,
            srcs = ["gn_link_repeat.cc", "gn_link_archive_api.cc"],
            copts = flags,
            target_compatible_with = compatible,
        )
        cc_library(
            name = "gn_forced_" + mode,
            srcs = ["gn_link_repeat.cc", "gn_link_constructor.cc"],
            alwayslink = True,
            copts = flags,
            target_compatible_with = compatible,
        )
        gn_executable_link_context(
            name = "gn_link_order_" + mode,
            deps = [":gn_lazy_" + mode, ":gn_forced_" + mode],
            target_compatible_with = compatible,
        )
        cc_test(
            name = "gn_link_" + mode + "_test",
            srcs = ["gn_link_main.cc"],
            copts = flags,
            linkopts = flags,
            target_compatible_with = compatible,
            deps = [":gn_link_order_" + mode],
        )

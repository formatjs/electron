"""Expose producer header settings without linking Node/V8 into addons."""

load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo", "merge_cc_infos")

def _impl(ctx):
    public = CcInfo(compilation_context = cc_common.create_compilation_context(
        defines = depset(ctx.attr.defines),
    ))
    merged = merge_cc_infos(cc_infos = [target[CcInfo] for target in ctx.attr.headers] + [public])
    return [
        CcInfo(compilation_context = merged.compilation_context),
        DefaultInfo(files = merged.compilation_context.headers),
    ]

electron_addon_sdk = rule(
    implementation = _impl,
    attrs = {
        "headers": attr.label_list(mandatory = True, providers = [CcInfo]),
        "defines": attr.string_list(),
    },
)

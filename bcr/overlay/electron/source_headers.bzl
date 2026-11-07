"""Forward native header context without linking the source libraries."""

load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

def _impl(ctx):
    merged = cc_common.merge_cc_infos(cc_infos = [dep[CcInfo] for dep in ctx.attr.deps])
    return [CcInfo(compilation_context = merged.compilation_context)]

electron_source_headers = rule(
    implementation = _impl,
    attrs = {"deps": attr.label_list(providers = [CcInfo])},
)

"""GN source sets precede lazy static archives at executable link boundaries."""

load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

def _impl(ctx):
    merged = cc_common.merge_cc_infos(cc_infos = [dep[CcInfo] for dep in ctx.attr.deps])
    forced = []
    lazy = []
    for linker_input in merged.linking_context.linker_inputs.to_list():
        kinds = [library.alwayslink for library in linker_input.libraries]
        if any(kinds) and not all(kinds):
            fail("GN link input mixes forced and lazy libraries: " + str(linker_input.owner))
        if any(kinds):
            forced.append(linker_input)
        else:
            lazy.append(linker_input)

    # Keep every source-set object, including unreferenced initializers. Resolving
    # these first avoids extracting their duplicate members from static archives.
    linking = cc_common.create_linking_context(
        linker_inputs = depset(forced + lazy, order = "topological"),
    )
    return [
        CcInfo(
            compilation_context = merged.compilation_context,
            linking_context = linking,
            debug_context = getattr(merged, "_debug_context", None),
            cc_native_library_info = struct(libraries_to_link = getattr(merged, "_legacy_transitive_native_libraries", depset())),
        ),
        DefaultInfo(
            files = depset(transitive = [dep[DefaultInfo].files for dep in ctx.attr.deps]),
            runfiles = ctx.runfiles().merge_all([dep[DefaultInfo].default_runfiles for dep in ctx.attr.deps]),
        ),
    ]

gn_executable_link_context = rule(
    implementation = _impl,
    attrs = {"deps": attr.label_list(providers = [CcInfo])},
)

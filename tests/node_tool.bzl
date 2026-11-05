"""Expose the declared execution Node file to generator integration tests."""

def _impl(ctx):
    node = ctx.toolchains["@rules_nodejs//nodejs:toolchain_type"].nodeinfo.node
    if not node:
        fail("Generator tests require a hermetic execution Node")
    return [DefaultInfo(files = depset([node]), runfiles = ctx.runfiles(files = [node]))]

execution_node = rule(implementation = _impl, toolchains = ["@rules_nodejs//nodejs:toolchain_type"])

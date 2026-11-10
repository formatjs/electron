"""Resolve generator Python after the dependency's execution transition."""

def _impl(ctx):
    return [ctx.toolchains["@rules_python//python:toolchain_type"]]

electron_execution_python = rule(
    implementation = _impl,
    toolchains = ["@rules_python//python:toolchain_type"],
    provides = [platform_common.ToolchainInfo],
)

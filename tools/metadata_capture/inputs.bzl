"""Pinned tools and SDKs used only by BB maintainer metadata capture."""

_PACKAGES = ["gn", "sysroot_x64", "sysroot_arm64", "rustc", "rust_std_x64", "rust_std_arm64", "chromium_tools"]

def _impl(ctx):
    content = ctx.read(ctx.attr.pins)
    pins = json.decode(content)
    if sorted(pins["packages"].keys()) != sorted(_PACKAGES):
        fail("Unexpected metadata capture package set")
    for name in _PACKAGES:
        package = pins["packages"][name]
        ctx.download_and_extract(
            url = package["url"],
            sha256 = package["sha256"],
            type = package["type"],
            stripPrefix = package.get("strip_prefix", ""),
            output = name,
        )
    ctx.file("capture_inputs.json", content)
    ctx.file("BUILD.bazel", 'exports_files(["capture_inputs.json"], visibility = ["//visibility:public"])\n')

capture_inputs = repository_rule(
    implementation = _impl,
    attrs = {"pins": attr.label(allow_single_file = True, mandatory = True)},
)

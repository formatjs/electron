"""Project only the pinned scanner, metadata and license texts."""

def _impl(ctx):
    inventory = json.decode(ctx.read(ctx.attr.inventory))
    roots = {}
    for anchor, prefix in ctx.attr.sources.items():
        ctx.read(anchor)
        roots[prefix] = ctx.path(anchor).dirname
    ctx.read(ctx.attr.chromium)
    chromium = ctx.path(ctx.attr.chromium).dirname
    vendor = ctx.path(ctx.attr.vendor).dirname
    for path in inventory["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid credits source path")
        if path in inventory["vendored_files"]:
            source = vendor.get_child(inventory["vendored_files"][path] + ".txt")
        else:
            source = chromium.get_child(path)
            matched = 0
            for prefix, root in roots.items():
                if len(prefix) > matched and path.startswith(prefix + "/"):
                    source = root.get_child(path[len(prefix) + 1:])
                    matched = len(prefix)
        if not source.exists:
            fail("Pinned credits source missing: " + path)
        ctx.symlink(source, path)
    ctx.file("inventory.bzl", "INVENTORY = json.decode(" + json.encode(ctx.read(ctx.attr.inventory)) + ")\n")
    ctx.file("BUILD.bazel", "package(default_visibility = [\"//visibility:public\"])\nexports_files(" + repr(sorted(inventory["files"]) + ["inventory.bzl"]) + ")\n")

electron_credits_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "sources": attr.label_keyed_string_dict(mandatory = True),
        "inventory": attr.label(default = Label("//source/native:credits_inputs.json")),
        "vendor": attr.label(default = Label("//source/license_data:BUILD.bazel")),
    },
)

"""Stable source fetch and overlay projection rules."""

load(":archive_urls.bzl", "source_archive_urls")

def _archive_impl(ctx):
    root = ctx.path(ctx.attr.catalog).dirname
    base = root.get_child("overlays/" + ctx.attr.overlay + "/bcr")
    source = json.decode(ctx.read(base.get_child("source.json")))
    ctx.download_and_extract(
        url = source_archive_urls(source["url"]),
        type = "tar.gz" if source["url"].endswith(".tar.gz") else "",
        integrity = source["integrity"],
        stripPrefix = source.get("strip_prefix", ""),
    )
    patches = base.get_child("patches")
    if patches.exists:
        ctx.watch_tree(patches)
        for patch in sorted(patches.readdir(), key = str):
            if not patch.is_dir:
                ctx.patch(patch, strip = source.get("patch_strip", 1))
    ctx.file("__source__/BUILD.bazel", 'exports_files(["anchor"])\n')
    ctx.file("__source__/anchor", ctx.attr.overlay)

_archive = repository_rule(
    implementation = _archive_impl,
    attrs = {
        "catalog": attr.label(mandatory = True),
        "overlay": attr.string(mandatory = True),
    },
)

def _sources_impl(ctx):
    root = ctx.path(ctx.attr.catalog).dirname
    overlay = root.get_child("overlays/" + ctx.attr.overlay + "/bcr/overlay")
    files = {}
    directories = {"": True}
    layers = [overlay]
    if ctx.attr.variant:
        layers.append(root.get_child("overlays/" + ctx.attr.overlay + "/platforms/" + ctx.attr.variant + "/overlay"))
    for layer in layers:
        ctx.watch_tree(layer)
        pending = [(layer, "")]
        for _ in range(32):
            next_level = []
            for directory, prefix in pending:
                for path in sorted(directory.readdir(), key = str):
                    relative = prefix + path.basename
                    if path.is_dir:
                        directories[relative] = True
                        next_level.append((path, relative + "/"))
                    else:
                        files[relative] = path
            pending = next_level
            if not pending:
                break
        if pending:
            fail("Overlay exceeds supported directory depth: " + str(layer))

    # Split only directories containing overrides; symlink unchanged source trees.
    # Rule edits then avoid extracting Chromium's archive again.
    source = ctx.path(ctx.attr.archive).dirname.dirname
    patched_files = {}
    for patch in ctx.attr.patches:
        lines = ctx.read(patch).splitlines()
        before = [line[6:].split("\t")[0] for line in lines if line.startswith("--- a/")]
        after = [line[6:].split("\t")[0] for line in lines if line.startswith("+++ b/")]
        if not after or before != after:
            fail("Source patches must modify existing a/ and b/ paths: " + str(patch))
        for relative in after:
            parts = relative.split("/")
            if not relative or relative.startswith("/") or ".." in parts:
                fail("Invalid patched source path: " + relative)
            patched_files[relative] = True
            if relative not in files:
                files[relative] = source.get_child(relative)
            for depth in range(1, len(parts)):
                directories["/".join(parts[:depth])] = True
    pending = [(source, "")]
    for _ in range(32):
        next_level = []
        for directory, prefix in pending:
            for path in sorted(directory.readdir(), key = str):
                relative = prefix + path.basename
                if path.is_dir and relative in directories:
                    next_level.append((path, relative + "/"))
                elif relative not in files:
                    ctx.symlink(path, relative)
        pending = next_level
        if not pending:
            break
    if pending:
        fail("Source exceeds supported directory depth: " + ctx.attr.overlay)
    for relative, path in files.items():
        if relative in patched_files:
            ctx.file(relative, ctx.read(path), executable = False)
        else:
            ctx.symlink(path, relative)
    for patch in ctx.attr.patches:
        ctx.patch(ctx.path(patch), strip = 1)

_sources = repository_rule(
    implementation = _sources_impl,
    attrs = {
        "archive": attr.label(mandatory = True),
        "catalog": attr.label(mandatory = True),
        "overlay": attr.string(mandatory = True),
        "patches": attr.label_list(allow_files = [".patch"]),
        "variant": attr.string(),
    },
)

electron_overlay_archive = _archive
electron_overlay_repository = _sources

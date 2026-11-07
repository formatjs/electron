"""Read-only projection of patched Node and original inspector/compression inputs."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "node": ctx.attr.node, "v8": ctx.attr.v8, "zstd": ctx.attr.zstd}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid libnode source path")
        owner = "chromium"
        relative = path
        original = profile["aliases"].get(path, path)
        for name, prefix in {"node": "third_party/electron_node/", "v8": "v8/", "zstd": "third_party/zstd/src/"}.items():
            if original.startswith(prefix):
                owner = name
                relative = original[len(prefix):]
        origin = roots[owner].get_child(relative)
        if path == "third_party/electron_node/src/api/embed_helpers.cc":
            ctx.file(path, ctx.read(origin), executable = False)
        else:
            ctx.symlink(origin, path)
    ctx.patch(ctx.attr.lifecycle_patch, strip = 1)
    ctx.file("native_compat_patches.json", json.encode({"graph_sha256": profile["graph_sha256"], "patches": [str(ctx.attr.lifecycle_patch)], "files": ["third_party/electron_node/src/api/embed_helpers.cc"]}))
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_libnode_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "node": attr.label(mandatory = True),
        "v8": attr.label(mandatory = True),
        "zstd": attr.label(mandatory = True),
        "lifecycle_patch": attr.label(default = Label("//source:node_embed_lifecycle.patch")),
        "profile": attr.label(default = Label("//source/native:libnode_inputs.json")),
        "build_file": attr.label(default = Label("//source:libnode.BUILD.bazel")),
    },
)

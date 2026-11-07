"""Read-only matching events sources and original GN metadata."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"chromium": ctx.attr.chromium, "snappy": ctx.attr.snappy, "protobuf_javascript": ctx.attr.protobuf_javascript, "perfetto": ctx.attr.perfetto}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid events source path")
        owner, relative = "chromium", path
        for prefix, name in {"third_party/snappy/src/": "snappy", "third_party/protobuf-javascript/src/": "protobuf_javascript", "third_party/perfetto/": "perfetto"}.items():
            if path.startswith(prefix):
                owner, relative = name, path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    for path, content in profile["generated_files"].items():
        if not path.startswith("//out/bazel-import/") or ".." in path.split("/"):
            fail("Invalid events metadata path")
        ctx.file(path[2:], content, executable = False)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_events_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "chromium": attr.label(mandatory = True),
        "snappy": attr.label(mandatory = True),
        "protobuf_javascript": attr.label(mandatory = True),
        "perfetto": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:events_inputs.json")),
        "build_file": attr.label(default = Label("//source:events.BUILD.bazel")),
    },
)

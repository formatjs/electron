"""Project the patched engine and pinned inspector/FP16 inputs read-only."""

def _impl(ctx):
    roots = {}
    for name, anchor in {"v8": ctx.attr.v8, "chromium": ctx.attr.chromium, "fp16": ctx.attr.fp16}.items():
        ctx.read(anchor)
        roots[name] = ctx.path(anchor).dirname
    contents = ctx.read(ctx.attr.profile)
    profile = json.decode(contents)
    for path in profile["files"]:
        if path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
            fail("Invalid V8 engine source path")
        owner = "chromium"
        relative = path
        for name, prefix in {"v8": "v8/", "fp16": "third_party/fp16/src/"}.items():
            if path.startswith(prefix):
                owner = name
                relative = path[len(prefix):]
        ctx.symlink(roots[owner].get_child(relative), path)
    ctx.file("profile.bzl", "PROFILE = json.decode(" + json.encode(contents) + ")\n")
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_v8_engine_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "v8": attr.label(mandatory = True),
        "chromium": attr.label(mandatory = True),
        "fp16": attr.label(mandatory = True),
        "profile": attr.label(default = Label("//source/native:v8_engine_inputs.json")),
        "build_file": attr.label(default = Label("//source:v8_engine.BUILD.bazel")),
    },
)

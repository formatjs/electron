"""Native XCB projection from checksum-pinned BCR source modules."""

def _impl(ctx):
    source = ctx.path(ctx.attr.source).dirname
    protocol = ctx.path(ctx.attr.protocol).dirname
    ctx.read(ctx.attr.source)
    ctx.read(ctx.attr.protocol)
    for path in source.get_child("src").readdir():
        if any([path.basename.endswith(suffix) for suffix in [".c", ".h", ".py", ".in"]]):
            ctx.symlink(path, "src/" + path.basename)
    for directory, suffix in [("src", ".xml"), ("xcbgen", ".py")]:
        for path in protocol.get_child(directory).readdir():
            if path.basename.endswith(suffix):
                ctx.symlink(path, "xcb-proto/" + directory + "/" + path.basename)
    ctx.file("native_provenance.json", json.encode({"source": "libxcb@1.17.0.bcr.3", "protocol": "xcb-proto@1.17.0", "configuration": "Linux AMD64; native abstract sockets"}))
    ctx.file("BUILD.bazel", ctx.read(ctx.attr.build_file))

electron_xcb_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "source": attr.label(mandatory = True),
        "protocol": attr.label(mandatory = True),
        "build_file": attr.label(default = Label("//source:xcb.BUILD.bazel")),
    },
)

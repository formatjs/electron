"""Compile integration schemas with the matching declared execution protoc."""

def _impl(ctx):
    outputs = []
    directory = None
    inputs = []
    for source in ctx.files.srcs:
        base = source.basename[:-len(".proto")]
        outputs += [ctx.actions.declare_file(ctx.label.name + "/" + base + ".pb.cc"), ctx.actions.declare_file(ctx.label.name + "/" + base + ".pb.h")]
        if directory != None and directory != source.dirname:
            fail("Probe schemas must share their declared import root")
        directory = source.dirname
        inputs.append(source.path)
    ctx.actions.run(
        executable = ctx.attr._protoc[DefaultInfo].files_to_run,
        arguments = ["--proto_path=" + directory, "--cpp_out=" + outputs[0].dirname] + inputs,
        inputs = ctx.files.srcs,
        outputs = outputs,
        env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronProtobuf",
    )
    return [
        DefaultInfo(files = depset(outputs)),
        OutputGroupInfo(sources = depset([file for file in outputs if file.extension == "cc"]), headers = depset([file for file in outputs if file.extension == "h"])),
    ]

electron_protobuf_probe = rule(
    implementation = _impl,
    attrs = {
        "srcs": attr.label_list(allow_files = [".proto"], mandatory = True),
        "_protoc": attr.label(default = Label("@electron_protobuf_sources//:protoc"), executable = True, cfg = "exec"),
    },
)

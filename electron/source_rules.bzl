"""Native Electron/Node generators with separate execution toolchains."""

def _js2c_impl(ctx):
    mappings = {}
    inputs = []
    for target, logical in ctx.attr.srcs.items():
        files = target.files.to_list()
        if len(files) != 1 or "\\" in logical or ":" in logical or not logical.startswith("lib/") or not logical.endswith(".js") or any([part in ["", ".", ".."] for part in logical.split("/")]):
            fail("js2c inputs require one JS file mapped beneath lib/: " + logical)
        if logical in mappings:
            fail("Duplicate js2c input: " + logical)
        mappings[logical] = files[0].path
        inputs.append(files[0])
    manifest = ctx.actions.declare_file(ctx.label.name + ".inputs.json")
    ctx.actions.write(manifest, json.encode(mappings))
    output = ctx.actions.declare_file(ctx.label.name + ".cc")
    args = ctx.actions.args()
    args.add_all(["--tool", ctx.executable._js2c, "--manifest", manifest, "--output", output])
    ctx.actions.run(executable = ctx.executable._runner, arguments = [args], inputs = inputs + [manifest], tools = [ctx.attr._js2c[DefaultInfo].files_to_run], outputs = [output], mnemonic = "ElectronJS2C")
    return [DefaultInfo(files = depset([output]))]

electron_js2c = rule(
    implementation = _js2c_impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = [".js"], mandatory = True),
        "_js2c": attr.label(default = Label("@electron_node_sources//:node_js2c"), executable = True, cfg = "exec"),
        "_runner": attr.label(default = Label("//electron/private:js2c"), executable = True, cfg = "exec"),
    },
)

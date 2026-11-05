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

def _fuses_impl(ctx):
    header = ctx.actions.declare_file(ctx.label.name + "/electron/fuses.h")
    implementation = ctx.actions.declare_file(ctx.label.name + "/electron/fuses.cc")
    debug_header = ctx.actions.declare_file(ctx.label.name + "/base/debug/debugging_buildflags.h")
    definitions = ctx.actions.declare_file(ctx.label.name + ".flags.rsp")
    ctx.actions.write(definitions, "--flags " + " ".join(ctx.attr.debug_flags))
    ctx.actions.run(executable = ctx.executable._runner, arguments = [ctx.file._fuses.path, header.path, implementation.path], inputs = [ctx.file._fuses, ctx.file._fuse_defaults], outputs = [header, implementation], mnemonic = "ElectronFuses")
    ctx.actions.run(executable = ctx.executable._runner, arguments = [ctx.file._buildflags.path, "--output", "base/debug/debugging_buildflags.h", "--rulename", "//base:debugging_buildflags", "--gen-dir", debug_header.dirname + "/../..", "--definitions", definitions.path], inputs = [ctx.file._buildflags, definitions], outputs = [debug_header], mnemonic = "ElectronBuildflags")
    return [DefaultInfo(files = depset([header, implementation, debug_header])), OutputGroupInfo(headers = depset([header, debug_header]), sources = depset([implementation]))]

electron_fuses_generate = rule(
    implementation = _fuses_impl,
    attrs = {
        "debug_flags": attr.string_list(mandatory = True),
        "_fuses": attr.label(default = Label("@electron_sources//:build/fuses/build.py"), allow_single_file = True),
        "_fuse_defaults": attr.label(default = Label("@electron_sources//:build/fuses/fuses.json5"), allow_single_file = True),
        "_buildflags": attr.label(default = Label("@electron_chromium_sources//:build/write_buildflag_header.py"), allow_single_file = True),
        "_runner": attr.label(default = Label("//electron/private:run_source"), executable = True, cfg = "exec"),
    },
)

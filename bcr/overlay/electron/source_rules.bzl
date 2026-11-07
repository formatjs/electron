"""Native Electron/Node generators with separate execution toolchains."""

NodeBuiltinFilesInfo = provider(fields = ["files"])

def _webpack_impl(ctx):
    node = ctx.toolchains["@rules_nodejs//nodejs:toolchain_type"].nodeinfo.node
    if not node:
        fail("Electron webpack requires a hermetic Node execution toolchain")
    mappings = {}
    packages = {}
    inputs = [ctx.file.lock, ctx.file.buildflags, ctx.file._driver, node]
    for target, logical in ctx.attr.srcs.items():
        files = target.files.to_list()
        if len(files) != 1 or logical in mappings or logical.startswith("/") or any([part in ["", ".", ".."] for part in logical.split("/")]) or "\\" in logical or ":" in logical:
            fail("Webpack input requires one file with unique relative path: " + logical)
        mappings[logical] = files[0].path
        inputs.append(files[0])
    for target, identity in ctx.attr.npm_packages.items():
        files = target.files.to_list()
        packages[identity] = files[0].owner.workspace_root
        inputs.extend(files)
    manifest = ctx.actions.declare_file(ctx.label.name + ".inputs.json")
    ctx.actions.write(manifest, json.encode({"sources": mappings, "packages": packages}))
    output = ctx.actions.declare_file(ctx.label.name + ".js")
    if ctx.attr.config not in mappings:
        fail("Webpack configuration must be a declared source input")
    arguments = ["--node", node.path, "--driver", ctx.file._driver.path, "--manifest", manifest.path, "--lock", ctx.file.lock.path, "--buildflags", ctx.file.buildflags.path, "--output", output.path, "--config", ctx.attr.config]
    ctx.actions.run(executable = ctx.executable._runner, arguments = arguments, inputs = inputs + [manifest], outputs = [output], mnemonic = "ElectronWebpack")
    return [DefaultInfo(files = depset([output]))]

electron_webpack = rule(
    implementation = _webpack_impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = True, mandatory = True),
        "npm_packages": attr.label_keyed_string_dict(mandatory = True),
        "lock": attr.label(allow_single_file = True, mandatory = True),
        "buildflags": attr.label(allow_single_file = True, mandatory = True),
        "config": attr.string(mandatory = True),
        "_driver": attr.label(default = Label("//electron/private:webpack.cjs"), allow_single_file = True),
        "_runner": attr.label(default = Label("//electron/private:webpack"), executable = True, cfg = "exec"),
    },
    toolchains = ["@rules_nodejs//nodejs:toolchain_type"],
)

def _buildflags_impl(ctx):
    output = ctx.actions.declare_file(ctx.label.name + "/electron/buildflags/buildflags.h")
    definitions = ctx.actions.declare_file(ctx.label.name + ".flags.rsp")
    ctx.actions.write(definitions, "--flags " + " ".join(ctx.attr.flags))
    ctx.actions.run(executable = ctx.executable._runner, arguments = [ctx.file._script.path, "--output", "electron/buildflags/buildflags.h", "--rulename", "//electron/buildflags:buildflags", "--gen-dir", output.dirname + "/../..", "--definitions", definitions.path], inputs = [ctx.file._script, definitions], outputs = [output], mnemonic = "ElectronBuildflags")
    return [DefaultInfo(files = depset([output]))]

electron_buildflags = rule(
    implementation = _buildflags_impl,
    attrs = {
        "flags": attr.string_list(mandatory = True),
        "_script": attr.label(default = Label("@electron_chromium_sources//:build/write_buildflag_header.py"), allow_single_file = True),
        "_runner": attr.label(default = Label("//electron/private:run_source"), executable = True, cfg = "exec"),
    },
)

def _js2c_impl(ctx):
    mappings = {}
    inputs = []
    for target, logical in ctx.attr.srcs.items():
        files = target.files.to_list()
        valid_prefix = logical.startswith("lib/") or (not ctx.file.config and logical.startswith("electron/js2c/")) or (ctx.file.config and logical.startswith("deps/"))
        valid_suffix = logical.endswith(".js") or (ctx.file.config and logical.endswith(".mjs"))
        if len(files) != 1 or "\\" in logical or ":" in logical or not valid_prefix or not valid_suffix or any([part in ["", ".", ".."] for part in logical.split("/")]):
            fail("js2c inputs require one JS file with a canonical builtin path: " + logical)
        if logical in mappings:
            fail("Duplicate js2c input: " + logical)
        mappings[logical] = files[0].path
        inputs.append(files[0])
    if ctx.attr.original_fs:
        for logical, file in ctx.attr.original_fs[NodeBuiltinFilesInfo].files.items():
            if logical in mappings:
                fail("Duplicate js2c input: " + logical)
            mappings[logical] = file.path
            inputs.append(file)
    manifest = ctx.actions.declare_file(ctx.label.name + ".inputs.json")
    ctx.actions.write(manifest, json.encode(mappings))
    output = ctx.actions.declare_file(ctx.label.name + ".cc")
    args = ctx.actions.args()
    args.add_all(["--tool", ctx.executable._js2c, "--manifest", manifest, "--output", output])
    if ctx.file.config:
        args.add_all(["--config", ctx.file.config])
        inputs.append(ctx.file.config)
    ctx.actions.run(executable = ctx.executable._runner, arguments = [args], inputs = inputs + [manifest], tools = [ctx.attr._js2c[DefaultInfo].files_to_run], outputs = [output], mnemonic = "ElectronJS2C")
    return [DefaultInfo(files = depset([output]))]

electron_js2c = rule(
    implementation = _js2c_impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = [".js", ".mjs"], mandatory = True),
        "config": attr.label(allow_single_file = [".gypi"]),
        "original_fs": attr.label(providers = [NodeBuiltinFilesInfo]),
        "_js2c": attr.label(default = Label("@electron_node_sources//:node_js2c"), executable = True, cfg = "exec"),
        "_runner": attr.label(default = Label("//electron/private:js2c"), executable = True, cfg = "exec"),
    },
)

def _original_fs_impl(ctx):
    inputs = []
    outputs = {}
    mappings = {}
    for target, logical in ctx.attr.srcs.items():
        files = target.files.to_list()
        if len(files) != 1 or not logical.startswith("lib/") or not logical.endswith(".js") or "\\" in logical or ":" in logical or any([part in ["", ".", ".."] for part in logical.split("/")]):
            fail("original-fs inputs require one JS file below lib/: " + logical)
        transformed = logical.replace("internal/fs/", "internal/original-fs/").replace("lib/fs.js", "lib/original-fs.js").replace("lib/fs/", "lib/original-fs/")
        if transformed == logical or transformed in outputs:
            fail("Invalid or duplicate original-fs output: " + logical)
        output = ctx.actions.declare_file(ctx.label.name + "/" + transformed)
        outputs[transformed] = output
        mappings[logical] = {"input": files[0].path, "output": transformed}
        inputs.append(files[0])
    manifest = ctx.actions.declare_file(ctx.label.name + ".inputs.json")
    ctx.actions.write(manifest, json.encode(mappings))
    if not outputs:
        fail("original-fs requires source files")
    output_root = "/".join([part for part in [ctx.bin_dir.path, ctx.label.workspace_root, ctx.label.package, ctx.label.name] if part])
    ctx.actions.run(executable = ctx.executable._runner, arguments = ["--script", ctx.file._script.path, "--manifest", manifest.path, "--output", output_root], inputs = inputs + [manifest, ctx.file._script], outputs = outputs.values(), mnemonic = "ElectronOriginalFS")
    return [DefaultInfo(files = depset(outputs.values())), NodeBuiltinFilesInfo(files = outputs)]

electron_original_fs = rule(
    implementation = _original_fs_impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = [".js"], mandatory = True),
        "_script": attr.label(default = Label("@electron//:script/node/generate_original_fs.py"), allow_single_file = True),
        "_runner": attr.label(default = Label("//electron/private:original_fs"), executable = True, cfg = "exec"),
    },
)

def _node_config_impl(ctx):
    output = ctx.actions.declare_file(ctx.label.name + "/config.gypi")
    ctx.actions.run(executable = ctx.executable._runner, arguments = ["--script", ctx.file._script.path, "--settings", ctx.file.settings.path, "--output", output.path], inputs = [ctx.file._script, ctx.file.settings] + ctx.files._support, outputs = [output], mnemonic = "ElectronNodeConfig")
    return [DefaultInfo(files = depset([output]))]

electron_node_config = rule(
    implementation = _node_config_impl,
    attrs = {
        "settings": attr.label(allow_single_file = [".json"], mandatory = True),
        "_script": attr.label(default = Label("@electron_node_sources//:tools/generate_config_gypi.py"), allow_single_file = True),
        "_support": attr.label_list(default = [Label("@electron_node_sources//:tools/getnapibuildversion.py"), Label("@electron_node_sources//:src/node_version.h")], allow_files = True),
        "_runner": attr.label(default = Label("//electron/private:node_config"), executable = True, cfg = "exec"),
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
        "_fuses": attr.label(default = Label("@electron//:build/fuses/build.py"), allow_single_file = True),
        "_fuse_defaults": attr.label(default = Label("@electron//:build/fuses/fuses.json5"), allow_single_file = True),
        "_buildflags": attr.label(default = Label("@electron_chromium_sources//:build/write_buildflag_header.py"), allow_single_file = True),
        "_runner": attr.label(default = Label("//electron/private:run_source"), executable = True, cfg = "exec"),
    },
)

def _node_defines_impl(ctx):
    push = ctx.actions.declare_file(ctx.label.name + "/electron/push_and_undef_node_defines.h")
    pop = ctx.actions.declare_file(ctx.label.name + "/electron/pop_node_defines.h")
    ctx.actions.run(executable = ctx.executable._runner, arguments = [ctx.file._script.path, push.dirname] + [header.path for header in ctx.files._headers], inputs = [ctx.file._script] + ctx.files._headers, outputs = [push, pop], mnemonic = "ElectronNodeDefines")
    return [DefaultInfo(files = depset([push, pop]))]

electron_node_defines = rule(
    implementation = _node_defines_impl,
    attrs = {
        "_script": attr.label(default = Label("@electron//:build/generate_node_defines.py"), allow_single_file = True),
        "_headers": attr.label_list(default = [Label("@electron_node_sources//:" + path) for path in ["src/tracing/trace_event_common.h", "src/tracing/trace_event.h", "src/util.h"]], allow_files = True),
        "_runner": attr.label(default = Label("//electron/private:run_source"), executable = True, cfg = "exec"),
    },
)

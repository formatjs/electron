"""Declared upstream Python actions with matching execution-platform tools."""

def _impl(ctx):
    mappings = {}
    for target, logical in ctx.attr.srcs.items():
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("Each logical generator input must identify one file")
        mappings[logical] = files[0]
    tools = []
    for target, logical in ctx.attr.tools.items():
        runner = target[DefaultInfo].files_to_run
        if logical in mappings:
            fail("Conflicting generator tool path")
        mappings[logical] = runner.executable
        tools.append(runner)
    manifest = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.write(manifest, json.encode({
        "inputs": [[file.path, logical] for logical, file in mappings.items()],
        "outputs": [[file.path, logical] for file, logical in zip(ctx.outputs.out_files, ctx.attr.logical_outputs)],
        "tools": ctx.attr.tools.values(),
        "script": ctx.attr.script,
        "args": ctx.attr.args,
        "response": ctx.attr.response,
        "verify_reproducible": ctx.attr.verify_reproducible,
    }))
    ctx.actions.run(
        executable = ctx.attr._runner[DefaultInfo].files_to_run,
        arguments = [manifest.path],
        inputs = depset(mappings.values() + [manifest], transitive = [target[DefaultInfo].files for target in ctx.attr.deps]),
        tools = tools,
        outputs = ctx.outputs.out_files,
        env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC", "PYTHONHASHSEED": "0"},
        mnemonic = "ElectronPython",
    )
    return [DefaultInfo(files = depset(ctx.outputs.out_files))]

electron_source_action = rule(
    implementation = _impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = True),
        "tools": attr.label_keyed_string_dict(cfg = "exec", allow_files = False),
        "deps": attr.label_list(),
        "out_files": attr.output_list(mandatory = True),
        "logical_outputs": attr.string_list(mandatory = True),
        "script": attr.string(mandatory = True),
        "args": attr.string_list(),
        "response": attr.string_list(),
        "verify_reproducible": attr.bool(default = True),
        "_runner": attr.label(default = Label("//electron/private:source_action"), executable = True, cfg = "exec"),
    },
)

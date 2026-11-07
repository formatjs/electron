"""Declared upstream Python actions with matching execution-platform tools."""

def _impl(ctx):
    mappings = {}
    for target, logical in ctx.attr.srcs.items():
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("Each logical generator input must identify one file")
        mappings[logical] = files[0]
    for target in ctx.attr.source_groups:
        root = target.label.workspace_root
        prefix = root + "/" if root else ""
        for file in target[DefaultInfo].files.to_list():
            if not file.is_source or not file.path.startswith(prefix):
                fail("Generator source groups must contain repository source files")
            logical = file.path[len(prefix):]
            if logical in mappings and mappings[logical] != file:
                fail("Conflicting generator source-group path")
            mappings[logical] = file
    tools = []
    for target, logical in ctx.attr.tools.items():
        runner = target[DefaultInfo].files_to_run
        if logical in mappings:
            fail("Conflicting generator tool path")
        if runner and runner.executable:
            mappings[logical] = runner.executable
            tools.append(runner)
        else:
            files = target[DefaultInfo].files.to_list()
            if len(files) != 1:
                fail("Generator file tools must identify one pinned executable")
            mappings[logical] = files[0]
            tools.append(files[0])
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
        "tools": attr.label_keyed_string_dict(cfg = "exec", allow_files = True),
        "source_groups": attr.label_list(cfg = "exec"),
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

"""Original Electron Node generators with locked npm inputs."""

def _relative(path):
    if not path or path.startswith("/") or "\\" in path or any([part in ["", ".", ".."] for part in path.split("/")]):
        fail("Expected canonical project-relative path: " + path)
    return path

def _node_project_impl(ctx):
    node = ctx.toolchains["@rules_nodejs//nodejs:toolchain_type"].nodeinfo.node
    if not node:
        fail("Electron Node generators require a hermetic Node execution toolchain")
    if len(ctx.outputs.out_files) != len(ctx.attr.logical_outputs) or not ctx.outputs.out_files:
        fail("Node outputs must match declared logical paths")
    sources, packages, outputs = {}, {}, {}
    inputs = [node, ctx.file.lock]
    for target, logical in ctx.attr.srcs.items():
        logical = _relative(logical)
        files = target.files.to_list()
        if len(files) != 1 or logical in sources:
            fail("Node source requires one file with a unique logical path")
        sources[logical] = files[0].path
        inputs.append(files[0])
    for target, identity in ctx.attr.npm_packages.items():
        files = target.files.to_list()
        if not files or identity in packages:
            fail("Node package identity requires one declared package tree")
        packages[identity] = files[0].owner.workspace_root
        inputs.extend(files)
    for logical, output in zip(ctx.attr.logical_outputs, ctx.outputs.out_files):
        logical = _relative(logical)
        if logical in outputs:
            fail("Duplicate Node output path")
        outputs[logical] = output.path
    project = _relative(ctx.attr.project)
    if project + "/yarn.lock" not in sources:
        fail("Node project must declare its original Yarn lock")
    commands = [json.decode(command) for command in ctx.attr.commands]
    if not commands:
        fail("Node project requires original generator commands")
    for command in commands:
        if type(command) != "list" or not command or any([type(value) != "string" for value in command]):
            fail("Expected Node entry point and argument list")
        _relative(command[0])
    if ctx.attr.version:
        logical = "out/bazel-import/args.gn"
        if logical in sources:
            fail("Duplicate Electron version metadata")
        metadata = ctx.actions.declare_file(ctx.label.name + ".args.gn")
        ctx.actions.write(metadata, "override_electron_version = " + json.encode(ctx.attr.version) + "\n")
        sources[logical] = metadata.path
        inputs.append(metadata)
    manifest = ctx.actions.declare_file(ctx.label.name + ".inputs.json")
    ctx.actions.write(manifest, json.encode(dict(sources = sources, packages = packages, outputs = outputs, project = project, commands = commands)))
    ctx.actions.run(
        executable = ctx.attr._runner[DefaultInfo].files_to_run,
        arguments = ["--node", node.path, "--manifest", manifest.path, "--lock", ctx.file.lock.path],
        inputs = depset(inputs + [manifest]),
        outputs = ctx.outputs.out_files,
        mnemonic = "ElectronNodeProject",
        env = {"PATH": "", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"},
    )
    return [DefaultInfo(files = depset(ctx.outputs.out_files))]

electron_node_project = rule(
    implementation = _node_project_impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = True, mandatory = True),
        "npm_packages": attr.label_keyed_string_dict(mandatory = True),
        "lock": attr.label(allow_single_file = True, mandatory = True),
        "project": attr.string(mandatory = True),
        "commands": attr.string_list(mandatory = True),
        "version": attr.string(),
        "logical_outputs": attr.string_list(mandatory = True),
        "out_files": attr.output_list(mandatory = True),
        "_runner": attr.label(default = Label("//electron/private:node_project"), executable = True, cfg = "exec"),
    },
    toolchains = ["@rules_nodejs//nodejs:toolchain_type"],
)

def _npm_file_impl(ctx):
    relative = _relative(ctx.attr.path)
    files = [file for file in ctx.files.package if file.path == file.owner.workspace_root + "/" + relative]
    if len(files) != 1:
        fail("Locked npm package must contain exactly one requested asset: " + relative)
    ctx.actions.symlink(output = ctx.outputs.out, target_file = files[0])
    return [DefaultInfo(files = depset([ctx.outputs.out]))]

electron_npm_file = rule(
    implementation = _npm_file_impl,
    attrs = {
        "package": attr.label(mandatory = True),
        "path": attr.string(mandatory = True),
        "out": attr.output(mandatory = True),
    },
)

"""Electron app layout and deterministic distribution packages."""

load("@with_cfg.bzl", "with_cfg")

ElectronRuntimeInfo = provider(fields = {"archive": "Runtime ZIP, including original licenses.", "platform": "Target platform.", "version": "Electron version."})
ElectronAppInfo = provider(fields = {"manifest": "App file mapping manifest.", "files": "Declared app inputs."})
_PLATFORMS = ["linux_amd64", "linux_arm64", "darwin_arm64", "windows_amd64", "windows_arm64"]

def _path(value):
    if not value or value.startswith("/") or "\\" in value or ":" in value or any([part in ["", ".", ".."] for part in value.split("/")]):
        fail("Expected relative app path: " + value)
    return value

def _runtime_impl(ctx):
    return [DefaultInfo(files = depset([ctx.file.archive])), ElectronRuntimeInfo(archive = ctx.file.archive, platform = ctx.attr.platform, version = ctx.attr.version)]

electron_runtime = rule(implementation = _runtime_impl, attrs = {"archive": attr.label(allow_single_file = [".zip"], mandatory = True), "platform": attr.string(values = _PLATFORMS, mandatory = True), "version": attr.string(mandatory = True)})

def _app_impl(ctx):
    package = ctx.actions.declare_file(ctx.label.name + ".package.json")
    main = _path(ctx.attr.main)
    mappings = {}
    files = []
    directories = []
    for target, destination in ctx.attr.srcs.items():
        source = target.files.to_list()
        if len(source) != 1:
            fail("srcs requires one file per label; bundle dependencies first: " + str(target.label))
        destination = _path(destination)
        if destination == "package.json" or destination in mappings:
            fail("Duplicate/reserved app path: " + destination)
        mappings[destination] = source[0].path
        files.append(source[0])
        if source[0].is_directory:
            directories.append(destination)
    if main not in mappings and not any([main.startswith(directory + "/") for directory in directories]):
        fail("App main missing from srcs: " + main)
    ctx.actions.write(package, json.encode({"name": ctx.attr.app_name, "version": ctx.attr.version, "main": main, "private": True}))
    mappings["package.json"] = package.path
    files.append(package)
    manifest = ctx.actions.declare_file(ctx.label.name + ".files.json")
    ctx.actions.write(manifest, json.encode(mappings))
    return [DefaultInfo(files = depset(files + [manifest])), ElectronAppInfo(manifest = manifest, files = depset(files))]

electron_app = rule(implementation = _app_impl, attrs = {"srcs": attr.label_keyed_string_dict(allow_files = True, mandatory = True), "app_name": attr.string(mandatory = True), "version": attr.string(mandatory = True), "main": attr.string(mandatory = True)})

def _package_impl(ctx):
    runtime = ctx.attr.runtime[ElectronRuntimeInfo]
    app = ctx.attr.app[ElectronAppInfo]
    output = ctx.actions.declare_file(ctx.label.name + ".zip")
    args = ctx.actions.args()
    args.add_all(["--runtime", runtime.archive, "--platform", runtime.platform, "--app-manifest", app.manifest, "--output", output, "--product-name", ctx.attr.product_name, "--bundle-id", ctx.attr.bundle_id])
    ctx.actions.run(executable = ctx.executable._packager, arguments = [args], inputs = depset([runtime.archive, app.manifest], transitive = [app.files]), outputs = [output], mnemonic = "ElectronPackage", progress_message = "Packaging Electron %s for %s" % (ctx.attr.product_name, runtime.platform), env = {"PYTHONHASHSEED": "0"})
    return [DefaultInfo(files = depset([output]))]

electron_package = rule(implementation = _package_impl, attrs = {"app": attr.label(providers = [ElectronAppInfo], mandatory = True), "runtime": attr.label(providers = [ElectronRuntimeInfo], default = "@electron_runtime//:runtime"), "product_name": attr.string(mandatory = True), "bundle_id": attr.string(mandatory = True), "_packager": attr.label(default = "//electron/private:package", executable = True, cfg = "exec")})

linux_amd64_package, _linux_amd64 = with_cfg(electron_package).set("platforms", [Label("//platforms:linux_amd64")]).build()
linux_arm64_package, _linux_arm64 = with_cfg(electron_package).set("platforms", [Label("//platforms:linux_arm64")]).build()
darwin_arm64_package, _darwin_arm64 = with_cfg(electron_package).set("platforms", [Label("//platforms:darwin_arm64")]).build()
windows_amd64_package, _windows_amd64 = with_cfg(electron_package).set("platforms", [Label("//platforms:windows_amd64")]).build()
windows_arm64_package, _windows_arm64 = with_cfg(electron_package).set("platforms", [Label("//platforms:windows_arm64")]).build()

def electron_packages(name, **kwargs):
    """Package same app for all five supported target platforms."""
    targets = []
    for platform, implementation in [("linux_amd64", linux_amd64_package), ("linux_arm64", linux_arm64_package), ("darwin_arm64", darwin_arm64_package), ("windows_amd64", windows_amd64_package), ("windows_arm64", windows_arm64_package)]:
        target = name + "_" + platform
        implementation(name = target, **kwargs)
        targets.append(":" + target)
    native.filegroup(name = name, srcs = targets)

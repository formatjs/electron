"""Exact bounded Electron webpack closure; install hooks never execute."""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

def _hub_impl(ctx):
    lines = ["package(default_visibility = [\"//visibility:public\"])"]
    for identity in ctx.attr.packages:
        lines.append("alias(name = %r, actual = %r)" % ("pkg_" + identity, "@electron_npm_" + identity + "//:files"))
    ctx.file("BUILD.bazel", "\n".join(lines))

_hub = repository_rule(implementation = _hub_impl, attrs = {"packages": attr.string_list()})

def _impl(ctx):
    packages = json.decode(ctx.read(Label("//source/native:webpack_lock.json")))["packages"]
    for identity, entry in packages.items():
        prefix = entry["name"].removeprefix("@types/") if entry["name"].startswith("@types/") else "package"
        http_archive(name = "electron_npm_" + identity, urls = [entry["url"]], integrity = entry["integrity"], strip_prefix = prefix, type = "tgz", build_file_content = "package(default_visibility = [\"//visibility:public\"])\nfilegroup(name = \"files\", srcs = glob([\"**\"], exclude = [\"BUILD.bazel\"]))")
    _hub(name = "electron_npm", packages = packages.keys())
    return ctx.extension_metadata(reproducible = True, root_module_direct_deps = ["electron_npm"], root_module_direct_dev_deps = [])

electron_npm = module_extension(implementation = _impl)

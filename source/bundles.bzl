"""Actual Electron webpack bundles and native embedder C++ registration."""

load("//electron:source_rules.bzl", "electron_js2c", "electron_webpack")
load("//source/native:webpack_inputs.bzl", "ELECTRON_BUNDLES", "WEBPACK_PACKAGES")

def electron_bundles():
    for name, bundle in ELECTRON_BUNDLES.items():
        electron_webpack(
            name = name,
            srcs = {"@electron_sources//:" + path: path for path in bundle["inputs"]},
            npm_packages = WEBPACK_PACKAGES,
            config = bundle["config"],
            lock = "//source/native:webpack_lock.json",
            buildflags = ":electron_buildflags",
            visibility = ["//visibility:public"],
        )
    electron_js2c(
        name = "electron_natives",
        srcs = {":" + name: "electron/js2c/" + name + ".js" for name in ELECTRON_BUNDLES},
        visibility = ["//visibility:public"],
    )
    native.filegroup(name = "electron_bundles", srcs = [":" + name for name in ELECTRON_BUNDLES])

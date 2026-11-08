# SPDX-License-Identifier: MIT
"""Capture Electron's original default-app commands and source inventories."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_electron_app_deps import capture as capture_packages


def capture(electron, graph_path):
    content = graph_path.read_bytes()
    targets = json.loads(gzip.decompress(content))["targets"]
    definitions = targets["//electron:build_electron_definitions"]
    javascript = targets["//electron:default_app_js"]
    archive = targets["//electron:default_app_asar"]
    expected = ["--silent", "gn-typescript-definitions", "--", "$SOURCE_ROOT/out/bazel-import/gen/electron/tsc/typings/electron.d.ts"]
    if definitions["args"] != expected or definitions["script"] != "//electron/build/npm-run.py":
        raise ValueError("Original declaration generator command changed")
    expected = ["--silent", "tsc", "--", "-p", "$SOURCE_ROOT/electron/tsconfig.default_app.json", "--outDir", "$SOURCE_ROOT/out/bazel-import/gen/electron/js/default_app/electron/default_app"]
    if javascript["args"] != expected or javascript["script"] != "//electron/build/npm-run.py":
        raise ValueError("Original default-app TypeScript command changed")
    if archive["script"] != "//electron/build/run-node.py" or archive["args"][0] != "$SOURCE_ROOT/electron/script/gn-asar.js":
        raise ValueError("Original default-app ASAR generator changed")
    metadata = json.loads((electron / "package.json").read_text())
    expected = "npm run create-api-json && electron-typescript-definitions --api=electron-api.json && node spec/ts-smoke/runner.js"
    if metadata["scripts"]["create-typescript-definitions"] != expected:
        raise ValueError("Original declaration validation pipeline changed")
    expected_scripts = {
        "create-api-json": "node script/create-api-json.mjs",
        "gn-typescript-definitions": "npm run create-typescript-definitions && node script/cp.mjs electron.d.ts",
        "tsc": "tsc",
    }
    if any(metadata["scripts"].get(name) != command for name, command in expected_scripts.items()):
        raise ValueError("Original default-app npm entry point changed")
    common = {"package.json", "yarn.lock"}
    declaration_sources = set()
    for original in definitions["inputs"]:
        path = original.removeprefix("//electron/")
        source = electron / path
        if source.is_dir():
            declaration_sources.update(file.relative_to(electron).as_posix() for file in source.rglob("*") if file.is_file())
        else:
            declaration_sources.add(path)
    declaration_sources.update(path.relative_to(electron).as_posix() for path in (electron / "spec/ts-smoke").rglob("*") if path.is_file())
    declaration_sources.update(["script/create-api-json.mjs", "script/lib/get-version.js", "script/lib/utils.js"])
    javascript_sources = {path.removeprefix("//electron/") for path in javascript["inputs"] + javascript["sources"]}
    static = {path.removeprefix("//electron/") for path in targets["//electron:default_app_static"]["sources"]}
    inventories = dict(declarations=sorted(declaration_sources | common), javascript=sorted(javascript_sources | common), archive=sorted(static | common | {"script/gn-asar.js"}))
    for paths in inventories.values():
        for path in paths:
            if path.startswith("/") or ".." in path.split("/") or not (electron / path).is_file():
                raise ValueError("Missing original default-app source: " + path)
    lock = capture_packages(electron)
    packages = {"@electron_npm//:pkg_" + key: key for key in lock["packages"]}
    return dict(packages=packages, octicons_package="@electron_npm//:pkg_" + lock["roots"]["@primer/octicons"], graph_sha256=hashlib.sha256(content).hexdigest(), sources=inventories, javascript_command=["node_modules/typescript/bin/tsc", *javascript["args"][3:]], archive_command=["script/gn-asar.js", *archive["args"][1:]], javascript_outputs=javascript["outputs"], archive_output=archive["outputs"][0], octicons=targets["//electron:default_app_octicon_deps"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("electron", "graph", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    data = capture(args.electron, args.graph)
    args.output.write_text('"""Original default-app commands and declared source inputs."""\n\nDEFAULT_APP = ' + repr(data) + "\n")
    print(json.dumps({key: len(paths) for key, paths in data["sources"].items()}))


if __name__ == "__main__":
    main()

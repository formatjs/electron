# SPDX-License-Identifier: MIT
"""Capture only Electron's webpack tool closure from its exact Yarn v1 lock."""
import argparse
import base64
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shlex


def parse_lock(text):
    entries = {}
    current = None
    section = None
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if not line.startswith(" "):
            current = {"dependencies": {}}
            for key in next(csv.reader([line[:-1]], skipinitialspace=True)):
                entries[key] = current
            section = None
        elif line.startswith("    "):
            if section in {"dependencies", "optionalDependencies"}:
                key, value = shlex.split(line)
                current["dependencies"][key] = value
        elif line.strip().endswith(":"):
            section = line.strip()[:-1]
        else:
            key, value = shlex.split(line)
            current[key] = value
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("electron", "graph", "lock", "inventory", "flags"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    lock = args.electron / "yarn.lock"
    entries = parse_lock(lock.read_text())
    package = json.loads((args.electron / "package.json").read_text())
    packages = {}

    def visit(name, requested):
        entry = entries[name + "@" + requested]
        url = entry["resolved"].split("#")[0]
        integrity = entry.get("integrity") or "sha1-" + base64.b64encode(bytes.fromhex(entry["resolved"].split("#")[1])).decode()
        identity = hashlib.sha256((url + integrity).encode()).hexdigest()[:20]
        if identity not in packages:
            if not url.startswith("https://registry.yarnpkg.com/"):
                raise ValueError("Webpack closure contains non-registry source: " + url)
            result = {"name": name, "version": entry["version"], "url": url, "integrity": integrity, "dependencies": {}}
            packages[identity] = result
            result["dependencies"] = {dep: visit(dep, version) for dep, version in entry["dependencies"].items()}
        return identity

    roots = {name: visit(name, package["devDependencies"][name]) for name in ("webpack", "ts-loader", "typescript", "wrapper-webpack-plugin", "buffer", "process", "events", "url", "null-loader", "timers-browserify")}
    roots["terser-webpack-plugin"] = packages[roots["webpack"]]["dependencies"]["terser-webpack-plugin"]
    roots["acorn"] = packages[roots["webpack"]]["dependencies"]["acorn"]
    graph = json.loads(gzip.decompress(args.graph.read_bytes()))
    bundles = {}
    for key, bundle in graph["targets"].items():
        if key.startswith("//electron:electron_") and key.endswith("_bundle"):
            filename = Path(bundle["outputs"][0]).name
            bundles[filename.removesuffix(".js")] = {"config": bundle["args"][4].removeprefix("$SOURCE_ROOT/electron/"), "inputs": sorted({path.removeprefix("//electron/") for path in bundle["inputs"]})}
    if len(bundles) != 8:
        raise ValueError("Expected eight actual Electron webpack targets")
    settings = {"yarn_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(), "graph_sha256": hashlib.sha256(args.graph.read_bytes()).hexdigest(), "roots": roots, "packages": dict(sorted(packages.items()))}
    args.lock.write_text(json.dumps(settings, indent=2) + "\n")
    args.inventory.write_text('"""Actual Electron bundle inputs and locked webpack packages."""\n\nWEBPACK_PACKAGES = ' + json.dumps({"@electron_npm//:pkg_" + key: key for key in sorted(packages)}, indent=4) + '\n\nELECTRON_BUNDLES = ' + json.dumps(dict(sorted(bundles.items())), indent=4) + '\n')
    flags = graph["targets"]["//electron/buildflags:buildflags"]["response_file_contents"][1:]
    args.flags.write_text('"""Actual Electron GN buildflags."""\n\nELECTRON_BUILD_FLAGS = ' + json.dumps(flags, indent=4) + '\n')
    print(f"Captured {len(packages)} locked packages, {len(bundles)} bundles")


if __name__ == "__main__":
    main()

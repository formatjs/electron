# SPDX-License-Identifier: MIT
"""Capture default-app and declaration tools from Electron's pinned Yarn lock."""

import argparse
import base64
import hashlib
import json
from pathlib import Path

from capture_webpack_deps import parse_lock


def capture(electron):
    lock = electron / "yarn.lock"
    entries = parse_lock(lock.read_text())
    metadata = json.loads((electron / "package.json").read_text())
    dependencies = metadata.get("dependencies", {}) | metadata.get("devDependencies", {})
    packages = {}

    def visit(name, requested):
        entry = entries[name + "@" + requested]
        url, _, digest = entry["resolved"].partition("#")
        integrity = entry.get("integrity") or "sha1-" + base64.b64encode(bytes.fromhex(digest)).decode()
        if not url.startswith("https://registry.yarnpkg.com/"):
            raise ValueError("Node tool package requires a pinned registry archive")
        identity = hashlib.sha256((url + integrity).encode()).hexdigest()[:20]
        if identity not in packages:
            row = dict(name=name, version=entry["version"], url=url, integrity=integrity, dependencies={})
            # Older DefinitelyTyped Node branches use a versioned archive root.
            if name == "@types/node" and entry["version"] == "20.16.12":
                row["strip_prefix"] = "node v20.16"
            packages[identity] = row
            row["dependencies"] = {dependency: visit(dependency, version) for dependency, version in entry["dependencies"].items()}
        return identity

    tools = {"@electron/docs-parser", "@electron/typescript-definitions", "@electron/asar", "@primer/octicons", "typescript", "webpack"}
    tools.update(name for name in dependencies if name.startswith("@types/"))
    roots = {name: visit(name, dependencies[name]) for name in sorted(tools)}
    return dict(yarn_lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(), roots=roots, packages=dict(sorted(packages.items())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--electron", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.electron)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(roots=len(result["roots"]), packages=len(result["packages"]))))


if __name__ == "__main__":
    main()

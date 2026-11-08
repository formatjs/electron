# SPDX-License-Identifier: MIT
"""Capture Electron's original Node generator dependencies from its Yarn lock."""

import argparse
import hashlib
import json
from pathlib import Path

from capture_webpack_deps import parse_lock


def capture(electron):
    lock = electron / "yarn.lock"
    entries = parse_lock(lock.read_text())
    metadata = json.loads((electron / "package.json").read_text())
    packages = {}
    roots = {}
    for name in ("semver",):
        requested = (metadata.get("devDependencies", {}) | metadata.get("dependencies", {}))[name]
        entry = entries[name + "@" + requested]
        if entry["dependencies"]:
            raise ValueError("Node generator package gained dependencies: " + name)
        url = entry["resolved"].split("#", 1)[0]
        integrity = entry["integrity"]
        if not url.startswith("https://registry.yarnpkg.com/") or not integrity.startswith("sha512-"):
            raise ValueError("Node generator package requires a pinned registry archive")
        identity = hashlib.sha256((url + integrity).encode()).hexdigest()[:20]
        packages[identity] = dict(name=name, version=entry["version"], url=url, integrity=integrity, dependencies={})
        roots[name] = identity
    return dict(yarn_lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(), roots=roots, packages=packages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--electron", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(capture(args.electron), indent=2) + "\n")


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Run original Node generators in a declared, reproducibility-checked project."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from npm_workspace import npm_workspace


def relative(value):
    if not value or value.startswith("/") or "\\" in value or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("Expected canonical project-relative path")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("node", "manifest", "lock"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    node = args.node.resolve()
    manifest = json.loads(args.manifest.read_text())
    lock = json.loads(args.lock.read_text())
    project = relative(manifest["project"])
    outputs = {relative(logical): Path(path).resolve() for logical, path in manifest["outputs"].items()}
    os.umask(0o022)
    expected = None
    for attempt in range(2):
        with npm_workspace(manifest, lock, project=project, prefix="electron-node-" + str(attempt) + "-") as root:
            for logical in manifest["sources"]:
                os.utime(root / relative(logical), (1600000000 + attempt * 100000000, ) * 2)
            for logical in outputs:
                (root / logical).parent.mkdir(parents=True, exist_ok=True)
            environment = {"HOME": str(root), "TMPDIR": str(root), "PATH": "", "TZ": "UTC", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "ELECTRON_OUT_DIR": "bazel-import"}
            for command in manifest["commands"]:
                if not command or not all(isinstance(value, str) for value in command):
                    raise ValueError("Expected a declared Node entry point and argument list")
                entry = root / project / relative(command[0])
                arguments = [value.replace("$SOURCE_ROOT", str(root)) for value in command[1:]]
                subprocess.run([str(node), str(entry), *arguments], cwd=root / project, env=environment, check=True)
            produced = {logical: (root / logical).read_bytes() for logical in outputs}
            if expected is not None and produced != expected:
                raise ValueError("Node generator output differs across source paths and mtimes")
            expected = produced
    for logical, destination in outputs.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(expected[logical])


if __name__ == "__main__":
    main()

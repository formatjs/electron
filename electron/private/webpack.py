# SPDX-License-Identifier: MIT
"""Stage exact locked npm packages and execute pinned Node's webpack API."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("node", "driver", "manifest", "lock", "buildflags", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    node, driver, output, flags = (path.resolve() for path in (args.node, args.driver, args.output, args.buildflags))
    manifest = json.loads(args.manifest.read_text())
    lock = json.loads(args.lock.read_text())
    with tempfile.TemporaryDirectory(prefix="electron-webpack-") as temporary:
        root = Path(temporary)
        for logical, source in manifest["sources"].items():
            destination = root / logical
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        if hashlib.sha256((root / "yarn.lock").read_bytes()).hexdigest() != lock["yarn_lock_sha256"]:
            raise ValueError("Electron yarn.lock differs from captured webpack closure")
        modules = root / "node_modules"
        store = modules / ".store"
        store.mkdir(parents=True)
        for identity, source in manifest["packages"].items():
            shutil.copytree(source, store / identity, ignore=shutil.ignore_patterns("BUILD.bazel"))
        for identity, package in lock["packages"].items():
            metadata = json.loads((store / identity / "package.json").read_text())
            if metadata["name"] != package["name"] or metadata["version"] != package["version"]:
                raise ValueError("Locked package identity mismatch: " + identity)
            if set(metadata.get("dependencies", {})) - set(package["dependencies"]):
                raise ValueError("Locked package dependency missing: " + package["name"])
            for name, dependency in package["dependencies"].items():
                destination = store / identity / "node_modules" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(store / dependency, target_is_directory=True)
        for name, identity in lock["roots"].items():
            destination = modules / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(store / identity, target_is_directory=True)
        shutil.copyfile(driver, root / "bazel-webpack.cjs")
        environment = {"HOME": str(root), "TMPDIR": str(root), "PATH": "", "TZ": "UTC", "LANG": "C.UTF-8"}
        subprocess.run([str(node), str(root / "bazel-webpack.cjs"), str(flags), str(output)], cwd=root, env=environment, check=True)


if __name__ == "__main__":
    main()

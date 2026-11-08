# SPDX-License-Identifier: MIT
"""Stage source files and exact npm packages without install hooks."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import tempfile


@contextmanager
def npm_workspace(manifest, lock, *, project="", prefix="electron-node-"):
    with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
        root = Path(temporary)
        project_root = root / project
        for logical, source in manifest["sources"].items():
            destination = root / logical
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        if hashlib.sha256((project_root / "yarn.lock").read_bytes()).hexdigest() != lock["yarn_lock_sha256"]:
            raise ValueError("Electron yarn.lock differs from captured Node closure")
        modules = project_root / "node_modules"
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
        yield root

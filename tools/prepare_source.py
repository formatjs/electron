# SPDX-License-Identifier: MIT
"""Prepare private GN maintainer metadata tree; never compile from this cache overlay."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path


def link_missing(source, destination):
    for entry in sorted(source.iterdir()):
        if entry.name in {"out", ".git", "BUILD.bazel", "MODULE.bazel", "__pycache__"}:
            continue
        target = destination / entry.name
        if not target.exists() and not target.is_symlink():
            target.symlink_to(entry.resolve(), target_is_directory=entry.is_dir())
        elif entry.is_dir() and target.is_dir() and not target.is_symlink():
            link_missing(entry, target)


def prepare(chromium, electron, node, v8, deps_cache, destination, dependencies=()):
    for directory in (chromium, electron, node, v8, deps_cache):
        if not directory.is_dir():
            raise ValueError(f"Missing source root: {directory}")
    if (chromium / "DEPS").read_bytes() != (deps_cache / "DEPS").read_bytes():
        raise ValueError("Dependency cache DEPS differs from pinned Chromium; use matching cache")
    expected = {"chromium": ("7efca501bfcc84657ba2921a852e98ce1fb37641", 144), "v8": ("bb294624702efbb17691b642333f06bf5108e600", 1)}
    for group, root in (("chromium", chromium), ("v8", v8)):
        provenance = json.loads((root / "electron_patches.json").read_text(encoding="utf-8"))
        revision, count = expected[group]
        if provenance["upstream_revision"] != revision or len(provenance["patches"]) != count:
            raise ValueError(f"Unexpected patched {group} provenance")
    shutil.copytree(chromium, destination, symlinks=True, copy_function=os.symlink)
    overlays = [("electron", electron), ("v8", v8), ("third_party/electron_node", node)]
    overlays.extend(dependencies)
    for name, root in overlays:
        target = destination / name
        if target.exists() or target.is_symlink():
            if target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(root, target_is_directory=True)
    link_missing(deps_cache, destination)
    # Chromium archives omit generated checkout metadata. Write private files,
    # never follow source/cache symlinks while updating the pinned revision.
    for name, text in {"build/util/LASTCHANGE": "LASTCHANGE=7efca501bfcc84657ba2921a852e98ce1fb37641\nLASTCHANGE_YEAR=2025\n"}.items():
        target = destination / name
        if target.is_symlink():
            target.unlink()
        target.write_text(text, encoding="utf-8")
    manifest = {"purpose": "GN maintainer metadata only; remaining Electron dependency patch stacks are not applied", "chromium_revision": expected["chromium"][0], "v8_revision": expected["v8"][0], "deps_sha256": hashlib.sha256((chromium / "DEPS").read_bytes()).hexdigest(), "deps_cache": str(deps_cache)}
    (destination / "electron-source-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("chromium", "electron", "node", "v8", "deps-cache", "destination"):
        parser.add_argument("--" + argument, type=Path, required=True)
    parser.add_argument("--dependency", action="append", default=[], metavar="RELATIVE_PATH=SOURCE_ROOT")
    arguments = vars(parser.parse_args())
    dependencies = []
    for value in arguments.pop("dependency"):
        name, root = value.split("=", 1)
        if Path(name).is_absolute() or ".." in Path(name).parts:
            parser.error("Dependency destination must stay below source root")
        dependencies.append((name, Path(root).resolve()))
    prepare(**{name: path.resolve() for name, path in arguments.items()}, dependencies=dependencies)


if __name__ == "__main__":
    main()

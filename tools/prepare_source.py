# SPDX-License-Identifier: MIT
"""Prepare a private GN metadata tree from pinned source repositories."""
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
from pathlib import Path


def checkout_args(chromium_deps, electron_deps):
    def assignments(path):
        return {target.id: node.value for node in ast.parse(path.read_text()).body if isinstance(node, ast.Assign)
                for target in node.targets if isinstance(target, ast.Name)}

    chromium, electron = assignments(chromium_deps), assignments(electron_deps)
    if (ast.literal_eval(chromium['gclient_gn_args_file']) != 'src/build/config/gclient_args.gni'
            or ast.literal_eval(electron['gclient_gn_args_from']) != 'src'):
        raise ValueError('Unexpected pinned checkout argument source')
    names = ast.literal_eval(chromium['gclient_gn_args'])
    if (not isinstance(names, list) or not all(isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name) for name in names)
            or len(set(names)) != len(names)):
        raise ValueError('Invalid pinned checkout argument names')
    values = {}
    for tree in (chromium, electron):
        variables = tree['vars']
        if not isinstance(variables, ast.Dict):
            raise ValueError('Expected pinned checkout variable dictionary')
        for key, value in zip(variables.keys, variables.values):
            if isinstance(key, ast.Constant) and key.value in names and (tree is chromium or key.value in values):
                values[key.value] = value
    lines = ['# Generated from pinned Chromium/Electron DEPS; no hooks run.']
    for name in names:
        value = values[name]
        if isinstance(value, ast.Constant) and type(value.value) is bool:
            literal = 'true' if value.value else 'false'
        elif (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'Str'
              and len(value.args) == 1 and not value.keywords):
            text = ast.literal_eval(value.args[0])
            if not isinstance(text, str) or '\n' in text or '\r' in text:
                raise ValueError('Invalid pinned checkout string')
            literal = '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$') + '"'
        else:
            raise ValueError('Unsupported pinned checkout argument expression')
        lines.append(name + ' = ' + literal)
    return '\n'.join(lines) + '\n'


def private_parents(destination, target):
    parents = []
    parent = target.parent
    while parent != destination:
        parents.append(parent)
        parent = parent.parent
    for parent in reversed(parents):
        if parent.is_symlink():
            source = parent.resolve()
            parent.unlink()
            parent.mkdir()
            for child in source.iterdir():
                (parent / child.name).symlink_to(child, target_is_directory=child.is_dir())
        elif not parent.exists():
            parent.mkdir()


def link_missing(source, destination):
    for entry in sorted(source.iterdir()):
        if entry.name in {"out", ".git", "BUILD.bazel", "MODULE.bazel", "__pycache__"}:
            continue
        target = destination / entry.name
        if not target.exists() and not target.is_symlink():
            target.symlink_to(entry.resolve(), target_is_directory=entry.is_dir())
        elif entry.is_dir() and target.is_dir() and not target.is_symlink():
            link_missing(entry, target)


def prepare(chromium, electron, node, v8, deps_cache, destination, dependencies=(), fingerprints=None):
    for directory in (chromium, electron, node, v8) + ((deps_cache,) if deps_cache is not None else ()):
        if not directory.is_dir():
            raise ValueError(f"Missing source root: {directory}")
    if deps_cache is not None and (chromium / "DEPS").read_bytes() != (deps_cache / "DEPS").read_bytes():
        raise ValueError("Dependency cache DEPS differs from pinned Chromium; use matching cache")
    expected = {"chromium": ("7efca501bfcc84657ba2921a852e98ce1fb37641", 144), "v8": ("bb294624702efbb17691b642333f06bf5108e600", 1)}
    for group, root in (("chromium", chromium), ("v8", v8)):
        provenance = json.loads((root / "electron_patches.json").read_text(encoding="utf-8"))
        revision, count = expected[group]
        if provenance["upstream_revision"] != revision or len(provenance["patches"]) != count:
            raise ValueError(f"Unexpected patched {group} provenance")
    overlays = [("electron", electron), ("v8", v8), ("third_party/electron_node", node)]
    overlays.extend(dependencies)
    applied = {"chromium", "node", "v8"}
    if fingerprints is not None:
        roots = {"": chromium, "electron": electron, "v8": v8, "third_party/electron_node": node, **dict(dependencies)}
        applied = set()
        for group, entry in fingerprints.items():
            root = roots.get(entry["source_path"])
            if root is None:
                continue
            for name, expected_hash in entry["files"].items():
                path = root / name
                actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
                if actual != expected_hash:
                    raise ValueError(f"Patched file differs: {group}/{name}")
            applied.add(group)
    for name, root in overlays:
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Dependency destination must stay below source root")
    generated_args = checkout_args(chromium / 'DEPS', electron / 'DEPS') if deps_cache is None else None
    shutil.copytree(chromium, destination, symlinks=True, copy_function=os.symlink)
    for name, root in overlays:
        target = destination / name
        # A nested dependency may live below a directory symlink (Squirrel's
        # Mantle/ReactiveObjC submodules). Materialize private parents first.
        private_parents(destination, target)
        if target.exists() or target.is_symlink():
            if target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(root, target_is_directory=True)
    if deps_cache is not None:
        link_missing(deps_cache, destination)
    # Chromium archives omit generated checkout metadata. Write private files,
    # never follow source/cache symlinks while updating the pinned revision.
    generated = {"build/util/LASTCHANGE": "LASTCHANGE=7efca501bfcc84657ba2921a852e98ce1fb37641\nLASTCHANGE_YEAR=2025\n"}
    if generated_args is not None:
        generated['build/config/gclient_args.gni'] = generated_args
    for name, text in generated.items():
        target = destination / name
        private_parents(destination, target)
        if target.is_symlink():
            target.unlink()
        target.write_text(text, encoding="utf-8")
    manifest = {"purpose": "GN maintainer metadata only; target code is not compiled here", "chromium_revision": expected["chromium"][0], "v8_revision": expected["v8"][0], "deps_sha256": hashlib.sha256((chromium / "DEPS").read_bytes()).hexdigest(), "deps_cache": str(deps_cache) if deps_cache is not None else None, "dependency_mode": "matching-DEPS-cache" if deps_cache is not None else "declared-only", "applied_patch_groups": sorted(applied)}
    (destination / "electron-source-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("chromium", "electron", "node", "v8", "destination"):
        parser.add_argument("--" + argument, type=Path, required=True)
    parser.add_argument("--deps-cache", type=Path, help="Optional matching-DEPS fallback; omit for declared inputs only")
    parser.add_argument("--dependency", action="append", default=[], metavar="RELATIVE_PATH=SOURCE_ROOT")
    parser.add_argument("--patch-fingerprints", type=Path)
    arguments = vars(parser.parse_args())
    fingerprints_path = arguments.pop("patch_fingerprints")
    fingerprints = json.loads(fingerprints_path.read_text(encoding="utf-8")) if fingerprints_path else None
    dependencies = []
    for value in arguments.pop("dependency"):
        name, root = value.split("=", 1)
        if Path(name).is_absolute() or ".." in Path(name).parts:
            parser.error("Dependency destination must stay below source root")
        dependencies.append((name, Path(root).resolve()))
    prepare(**{name: path.resolve() if path is not None else None for name, path in arguments.items()}, dependencies=dependencies, fingerprints=fingerprints)


if __name__ == "__main__":
    main()

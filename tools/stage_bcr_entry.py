#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize one Electron version from the maintained BCR overlay."""

import argparse
import base64
import hashlib
import json
import pathlib
import re
import shutil

VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


def _read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def _integrity(path: pathlib.Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).digest()
    return "sha256-" + base64.b64encode(digest).decode()


def _stamp_module(template: str, version: str) -> str:
    marker = 'version = ""'
    if template.count(marker) != 1:
        raise ValueError("BCR MODULE.bazel needs one blank version")
    return template.replace(marker, f'version = "{version}"')


def stage_entry(
    source_registry: pathlib.Path,
    target_registry: pathlib.Path,
    module: str,
    version: str,
) -> pathlib.Path:
    if module != "electron" or not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"invalid module or version: {module}@{version}")

    source_metadata = _read_json(source_registry / "metadata.json")
    if version not in source_metadata["versions"]:
        raise ValueError(f"{module}@{version} missing from source metadata")

    target_module = target_registry / "modules" / module
    target_version = target_module / version
    target_metadata_path = target_module / "metadata.json"
    target_metadata = (
        _read_json(target_metadata_path) if target_metadata_path.is_file() else {}
    )
    if target_version.exists() or version in target_metadata.get("versions", []):
        raise ValueError(f"{module}@{version} already exists in target registry")

    template = (source_registry / "MODULE.bazel").read_text()
    if any(call in template for call in ("_override(", "register_toolchains(")):
        raise ValueError("published MODULE.bazel contains development-only calls")
    published_module = _stamp_module(template, version)
    source = _read_json(source_registry / "source.json")

    target_module.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_registry / "overlay", target_version / "overlay",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "bazel-*", "MODULE.bazel.lock"),
    )
    if (source_registry / "patches").is_dir():
        shutil.copytree(source_registry / "patches", target_version / "patches")
    (target_version / "MODULE.bazel").write_text(published_module)
    (target_version / "overlay" / "MODULE.bazel").write_text(published_module)
    shutil.copyfile(source_registry / "presubmit.yml", target_version / "presubmit.yml")
    source["overlay"] = {
        path.relative_to(target_version / "overlay").as_posix(): _integrity(path)
        for path in sorted((target_version / "overlay").rglob("*"))
        if path.is_file()
    }
    source["patch_strip"] = 1
    source["patches"] = {
        path.relative_to(target_version / "patches").as_posix(): _integrity(path)
        for path in sorted((target_version / "patches").rglob("*"))
        if path.is_file()
    }
    (target_version / "source.json").write_text(json.dumps(source, indent=4) + "\n")

    metadata = dict(source_metadata)
    metadata["versions"] = [*target_metadata.get("versions", []), version]
    metadata["yanked_versions"] = {
        **target_metadata.get("yanked_versions", {}),
        **source_metadata.get("yanked_versions", {}),
    }
    target_metadata_path.write_text(json.dumps(metadata, indent=4) + "\n")
    return target_version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-registry", type=pathlib.Path, required=True)
    parser.add_argument("--target-registry", type=pathlib.Path, required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    staged = stage_entry(
        args.source_registry,
        args.target_registry,
        args.module,
        args.version,
    )
    print(f"staged {args.module}@{args.version} at {staged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

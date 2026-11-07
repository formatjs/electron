#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate source pins, the isolated consumer and staged registry contents."""

import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.stage_bcr_entry import stage_entry


def integrity(path):
    return "sha256-" + base64.b64encode(hashlib.sha256(path.read_bytes()).digest()).decode()


def main():
    source = ROOT / "bcr"
    metadata = json.loads((source / "metadata.json").read_text())
    version = metadata["versions"][-1]
    template = (source / "MODULE.bazel").read_text()
    if template != (source / "overlay/MODULE.bazel").read_text():
        raise ValueError("registry and overlay MODULE.bazel templates differ")
    if 'name = "electron"' not in template or '">=9.2.0"' not in template:
        raise ValueError("published module must be electron, requiring Bazel 9.2.0")

    development = (ROOT / "MODULE.bazel").read_text()
    if 'name = "electron_development"' not in development:
        raise ValueError("development workspace must have a separate module name")
    dependency = f'bazel_dep(name = "electron", version = "{version}")'
    if dependency not in development:
        raise ValueError("development module must consume the proposed registry version")

    pin = json.loads((source / "source.json").read_text())
    digest = base64.b64decode(pin["integrity"].removeprefix("sha256-"), validate=True)
    if not pin["integrity"].startswith("sha256-") or len(digest) != 32:
        raise ValueError("source archive needs SHA256 integrity")
    release = pin["strip_prefix"].removeprefix("electron-")
    if not (version == release or version.startswith(release + ".bcr.")) or not pin["url"].endswith(f"/v{release}.tar.gz"):
        raise ValueError("source archive version differs from proposed module")
    extension = (source / "overlay/electron/extensions.bzl").read_text()
    if f'_VERSION = "{release}"' not in extension:
        raise ValueError("dependency extension differs from the source release")
    if not re.search(r'version\s*=\s*"' + re.escape(version) + r'"', development):
        raise ValueError("development module version differs from proposal")

    consumer = ROOT / "tests/bcr"
    published_consumer = source / "overlay/tests/bcr"
    ignored = {"MODULE.bazel.lock", "__pycache__"}
    for path in consumer.rglob("*"):
        relative = path.relative_to(consumer)
        if any(part in ignored or part.startswith("bazel-") for part in relative.parts):
            continue
        if path.is_file() and path.read_bytes() != (published_consumer / relative).read_bytes():
            raise ValueError(f"published consumer differs: {relative}")
    if (ROOT / "platforms/BUILD.bazel").read_bytes() != (consumer / "platforms/BUILD.bazel").read_bytes():
        raise ValueError("consumer execution platform differs from development")

    with tempfile.TemporaryDirectory() as temporary:
        registry = Path(temporary)
        existing = registry / "modules/electron"
        previous = "38.0.0"
        (existing / previous).mkdir(parents=True)
        sentinel = existing / previous / "MODULE.bazel"
        sentinel.write_text("preserve published entry\n")
        (existing / "metadata.json").write_text(json.dumps({
            "versions": [previous], "yanked_versions": {previous: "preserved reason"},
        }))
        staged = stage_entry(source, registry, "electron", version)
        merged = json.loads((existing / "metadata.json").read_text())
        if merged["versions"] != [previous, version] or sentinel.read_text() != "preserve published entry\n":
            raise ValueError("staging changed a published entry")
        if merged["yanked_versions"].get(previous) != "preserved reason":
            raise ValueError("staging lost published yank metadata")
        module = (staged / "MODULE.bazel").read_bytes()
        if module != (staged / "overlay/MODULE.bazel").read_bytes():
            raise ValueError("staged module files differ")
        manifest = json.loads((staged / "source.json").read_text())
        for kind in ("overlay", "patches"):
            files = {
                path.relative_to(staged / kind).as_posix(): integrity(path)
                for path in (staged / kind).rglob("*") if path.is_file()
            }
            if manifest[kind] != files:
                raise ValueError(f"staged {kind} integrity differs")
        try:
            stage_entry(source, registry, "electron", version)
        except ValueError as error:
            if "already exists" not in str(error):
                raise
        else:
            raise ValueError("staging overwrote an immutable version")

    print(f"BCR overlay staging valid: electron@{version}")
    if not metadata["maintainers"]:
        print("Publication pending: maintainer metadata")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)

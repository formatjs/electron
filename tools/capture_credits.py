# SPDX-License-Identifier: MIT
"""Capture original Chromium license discovery; never generate product HTML."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

OVERLAY = Path(__file__).resolve().parents[1] / "bcr/overlay"
sys.path.insert(0, str(OVERLAY / "source/credits"))
from credits_inputs import discover

SOURCES = [
    "DEPS",
    "build/action_helpers.py",
    "build/gn_helpers.py",
    "tools/licenses/licenses.py",
    "tools/licenses/spdx_writer.py",
    "components/webui/about/resources/about_credits.tmpl",
    "components/webui/about/resources/about_credits_entry.tmpl",
    "components/webui/about/resources/about_credits_reciprocal.tmpl",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--vendor", action="append", default=[])
    args = parser.parse_args()
    root = args.source_root.resolve()
    sys.path.insert(0, str(root / "tools/licenses"))
    spec = importlib.util.spec_from_file_location("licenses", root / "tools/licenses/licenses.py")
    licenses = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(licenses)
    directories, files, metadata = discover(licenses, root)
    if any(entry["shipped"] != licenses.NO and not entry["licenses"] for entry in metadata):
        raise ValueError("Shipped dependency lacks license text")
    files = sorted(set(files + SOURCES))
    if not set(args.vendor) <= set(files):
        raise ValueError("Vendored path is outside the discovered closure")
    hashes = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in files}
    from native_graph import unpack_profile
    profile = unpack_profile(json.loads((OVERLAY / "source/native/platform_inputs.json").read_text()))
    runtime = json.loads((OVERLAY / "source/native/runtime_inputs.json").read_text())
    producer = runtime["producers"]["//components/resources:about_credits"]
    if producer["script"] != "//tools/licenses/licenses.py" or producer["type"] != "action":
        raise ValueError("Expected the original credits action")
    inventory = {
        "directories": directories,
        "metadata": metadata,
        "files": hashes,
        "vendored_files": {path: hashes[path] for path in sorted(args.vendor)},
        "source_revisions": profile["source_revisions"],
        "upstream_pins_sha256": hashlib.sha256((OVERLAY / "source/upstream_pins.json").read_bytes()).hexdigest(),
        "producer": producer,
        "gn_project_sha256": runtime["gn_project_sha256"],
    }
    data = OVERLAY / "source/license_data"
    data.mkdir(exist_ok=True)
    for path in args.vendor:
        (data / (hashes[path] + ".txt")).write_bytes((root / path).read_bytes())
    (OVERLAY / "source/native/credits_inputs.json").write_text(json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"directories": len(directories), "records": len(metadata), "inputs": len(files), "vendored": len(args.vendor)}))


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Run Chromium's unmodified credits generator over its pinned input closure."""

import hashlib
import json
from pathlib import Path
import runpy
import sys

import credits_inputs
import licenses


def main():
    root = Path(__file__).resolve().parents[2]
    inventory = json.loads((root / "tools/licenses/credits_inputs.json").read_text())
    if hashlib.sha256((root / "tools/licenses/upstream_pins.json").read_bytes()).hexdigest() != inventory["upstream_pins_sha256"]:
        raise ValueError("Recapture credits after changing upstream source pins")
    for path, digest in inventory["files"].items():
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
            raise ValueError("Pinned credits input changed: " + path)
    directories, _, records = credits_inputs.discover(licenses, root)
    if directories != inventory["directories"] or records != inventory["metadata"]:
        raise ValueError("Credits discovery differs from the complete pinned checkout")
    sys.argv[0] = str(root / "tools/licenses/licenses.py")
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()

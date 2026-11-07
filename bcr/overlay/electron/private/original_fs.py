# SPDX-License-Identifier: MIT
"""Run Electron's original-fs generator in its expected private source layout."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("script", "manifest", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    script, output = args.script.resolve(), args.output.resolve()
    files = json.loads(args.manifest.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="electron-original-fs-") as temporary:
        root = Path(temporary)
        for logical, entry in files.items():
            source = root / "third_party/electron_node" / logical
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(entry["input"], source)
            (output / entry["output"]).parent.mkdir(parents=True, exist_ok=True)
        working = root / "electron/script"
        working.mkdir(parents=True)
        os.chdir(working)
        sys.argv = [str(script), str(output), *files]
        runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()

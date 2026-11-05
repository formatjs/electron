# SPDX-License-Identifier: MIT
"""Stage declared JS inputs under stable Node builtin names."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("tool", "manifest", "output"):
        parser.add_argument("--" + argument, type=Path, required=True)
    args = parser.parse_args()
    tool, output = args.tool.resolve(), args.output.resolve()
    files = json.loads(args.manifest.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="electron-js2c-") as temporary:
        root = Path(temporary)
        for logical, filename in files.items():
            destination = root / logical
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(filename, destination)
        subprocess.run([str(tool), "--only-js", str(output), *sorted(files)], cwd=root, check=True)


if __name__ == "__main__":
    main()

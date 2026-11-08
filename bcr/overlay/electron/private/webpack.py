# SPDX-License-Identifier: MIT
"""Stage exact locked npm packages and execute pinned Node's webpack API."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from npm_workspace import npm_workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("node", "driver", "manifest", "lock", "buildflags", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    node, driver, output, flags = (path.resolve() for path in (args.node, args.driver, args.output, args.buildflags))
    manifest = json.loads(args.manifest.read_text())
    lock = json.loads(args.lock.read_text())
    with npm_workspace(manifest, lock, prefix="electron-webpack-") as root:
        shutil.copyfile(driver, root / "bazel-webpack.cjs")
        environment = {"HOME": str(root), "TMPDIR": str(root), "PATH": "", "TZ": "UTC", "LANG": "C.UTF-8"}
        subprocess.run([str(node), str(root / "bazel-webpack.cjs"), str(flags), str(output), args.config], cwd=root, env=environment, check=True)


if __name__ == "__main__":
    main()

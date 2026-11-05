# SPDX-License-Identifier: MIT
"""Record modified source hashes after Bazel verifies and applies patch stacks."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--electron", type=Path, required=True)
    parser.add_argument("--repositories", type=Path, required=True)
    parser.add_argument("--dependency-repositories", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {}
    for entry in json.loads(args.pins.read_text(encoding="utf-8")):
        group = entry["group"]
        name = "electron_" + group.lower().replace(".", "_").replace("-", "_") + "_sources"
        repositories = args.repositories if group in {"chromium", "node", "v8"} else args.dependency_repositories
        root = repositories / ("+electron+" + name)
        if not root.is_dir():
            raise FileNotFoundError(root)
        modified = set()
        for patch in entry["patches"]:
            for line in (args.electron / "patches" / group / patch).read_text(encoding="utf-8").splitlines():
                if line.startswith("diff --git "):
                    modified.add(shlex.split(line)[3].removeprefix("b/"))
        if not modified:
            raise ValueError(f"No patched files recorded: {group}")
        result[group] = {"source_path": entry["repo"].removeprefix("src").lstrip("/"), "url": entry["url"], "patch_count": len(entry["patches"]), "files": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() if (root / name).exists() else None for name in sorted(modified)}}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(result)} groups, {sum(len(group['files']) for group in result.values())} patched files")


if __name__ == "__main__":
    main()

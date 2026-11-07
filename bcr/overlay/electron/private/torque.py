# SPDX-License-Identifier: MIT
"""Run the pinned Torque compiler using declared inputs and stable logical paths."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile


def relative(path):
    value = PurePosixPath(path)
    if not value.parts or value.is_absolute() or str(value) != path or ".." in value.parts or "\\" in path or ":" in path:
        raise ValueError("Invalid Torque path")
    return path


def generate(description):
    inputs = {relative(name): Path(path).absolute() for name, path in description["inputs"].items()}
    if sorted(description["sources"]) != sorted(inputs):
        raise ValueError("Torque source order differs from declared inputs")
    outputs = {}
    for logical, target in description["outputs"].items():
        relative(logical)
        if not logical.startswith("torque-generated/"):
            raise ValueError("Unexpected Torque output root")
        outputs[logical] = target
    tool = str(Path(description["tool"]).absolute())
    with tempfile.TemporaryDirectory(prefix="electron-torque-") as directory:
        directory = Path(directory)

        def run(name, mtime):
            root = directory / name / "source with spaces"
            output = directory / name / "generated with spaces"
            output.mkdir(parents=True)
            for logical in outputs:
                (output / logical.removeprefix("torque-generated/")).parent.mkdir(parents=True, exist_ok=True)
            for logical, source in inputs.items():
                destination = root / logical
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                os.utime(destination, (mtime, mtime))
            # Torque embeds this root in generated source locations.
            subprocess.run([tool, "-o", str(output), "-v8-root", ".", *description["sources"]], cwd=root, check=True)
            return output

        first = run("first", 0)
        second = run("repeat", 1234567890) if description["verify_reproducible"] else None
        records = []
        for logical, target in sorted(outputs.items()):
            name = logical.removeprefix("torque-generated/")
            source = first / name
            data = source.read_bytes()
            if second is not None and data != (second / name).read_bytes():
                raise ValueError("Torque output differs across paths and input mtimes")
            output = Path(target)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
            records.append({"path": logical, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        report = {"source_count": len(inputs), "output_count": len(records), "profile_sha256": description["profile_sha256"], "reproducibility_checked": second is not None, "files": records}
        Path(description["report"]).write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    generate(json.loads(Path(sys.argv[1]).read_text()))

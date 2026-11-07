# SPDX-License-Identifier: MIT
"""Execute original generators using only declared logical inputs and tools."""

import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys
import tempfile


def logical_path(root, value):
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in (".", "..") for part in path.parts) or "\\" in value:
        raise ValueError("Invalid generator logical path")
    return root.joinpath(*path.parts)


def generate(manifest, repeat):
    execution_root = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="electron generator repeat " if repeat else "electron-generator-") as directory:
        root = Path(directory)
        tools, seen = set(manifest["tools"]), set()
        for actual, logical in manifest["inputs"]:
            if logical in seen:
                raise ValueError("Duplicate generator logical input")
            seen.add(logical)
            source = execution_root / actual
            destination = logical_path(root, logical)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if logical in tools:
                destination.symlink_to(source)
            else:
                shutil.copyfile(source, destination)
                os.utime(destination, (918273645 if repeat else 123456789, ) * 2)
        build = root / "out/bazel-import"
        build.mkdir(parents=True, exist_ok=True)
        for _, logical in manifest["outputs"]:
            logical_path(build, logical).parent.mkdir(parents=True, exist_ok=True)
        response = build / "action.rsp"
        response.write_text(shlex.join(manifest["response"]))
        arguments = [arg.replace("{{response_file_name}}", str(response)) for arg in manifest["args"]]
        if any("{{" in arg or "$LLVM_ROOT" in arg for arg in arguments):
            raise ValueError("Unresolved generator argument")
        scratch = root / "tmp"
        scratch.mkdir()
        environment = {"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "TMPDIR": str(scratch), "PYTHONHASHSEED": "0", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        bootstrap = "import os, runpy, sys; script = sys.argv[1]; sys.argv = sys.argv[1:]; sys.path.insert(0, os.path.dirname(os.path.abspath(script))); runpy.run_path(script, run_name='__main__')"
        result = subprocess.run([sys.executable, "-I", "-B", "-c", bootstrap, str(logical_path(root, manifest["script"])), *arguments], cwd=build, env=environment)
        if result.returncode:
            raise SystemExit(result.returncode)
        return {logical: logical_path(build, logical).read_bytes() for _, logical in manifest["outputs"]}


def run(manifest):
    outputs = generate(manifest, False)
    if manifest["verify_reproducible"] and outputs != generate(manifest, True):
        raise ValueError("Generator output differs across source paths and mtimes: " + manifest["script"])
    for actual, logical in manifest["outputs"]:
        Path(actual).write_bytes(outputs[logical])


if __name__ == "__main__":
    run(json.loads(Path(sys.argv[1]).read_text()))

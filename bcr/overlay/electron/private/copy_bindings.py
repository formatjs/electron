# SPDX-License-Identifier: MIT
"""Stage original generated bindings for Chromium's namespace wrapper."""

from pathlib import Path
import shutil
import sys

output = Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
filename = sys.argv[3] if len(sys.argv) > 3 else "bindings.rs"
if Path(filename).name != filename or not filename.endswith(".rs") or "\\" in filename:
    raise ValueError("Expected one generated Rust filename")
shutil.copyfile(sys.argv[1], output / filename)

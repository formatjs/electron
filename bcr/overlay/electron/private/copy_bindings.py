# SPDX-License-Identifier: MIT
"""Stage original generated bindings for Chromium's namespace wrapper."""

from pathlib import Path
import shutil
import sys

output = Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
shutil.copyfile(sys.argv[1], output / "bindings.rs")

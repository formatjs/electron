# SPDX-License-Identifier: MIT
"""Copy declared bytes into a regular file; runtime loaders resolve symlinks."""

import os
from pathlib import Path
import sys
import shutil

source, output = map(Path, sys.argv[1:])
output.unlink(missing_ok=True)
shutil.copyfile(source, output)
os.chmod(output, 0o644)

# SPDX-License-Identifier: MIT
"""Copy declared bytes into a regular file; runtime loaders resolve symlinks."""

import os
from pathlib import Path
import sys
import shutil

source, output = map(Path, sys.argv[1:3])
output.unlink(missing_ok=True)
shutil.copyfile(source, output)
os.chmod(output, 0o755 if len(sys.argv) > 3 and sys.argv[3] == "1" else 0o644)
os.utime(output, (0, 0))

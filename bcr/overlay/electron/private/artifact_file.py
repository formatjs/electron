# SPDX-License-Identifier: MIT
"""Copy declared bytes into a regular file; runtime loaders resolve symlinks."""

import os
from pathlib import Path
import sys

source, output = map(Path, sys.argv[1:])
output.write_bytes(source.read_bytes())
os.chmod(output, 0o644)

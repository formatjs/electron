# SPDX-License-Identifier: MIT
"""Copy declared generator executables and adjacent runtime data."""

import json
import os
from pathlib import Path
import shutil
import sys

for source, destination, executable in json.loads(Path(sys.argv[1]).read_text()):
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    output.chmod(0o755 if executable else 0o644)
    os.utime(output, (0, 0))

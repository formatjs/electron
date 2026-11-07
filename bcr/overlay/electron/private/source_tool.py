# SPDX-License-Identifier: MIT
"""Stage declared runtime data beside a native generator."""

import json
import os
from pathlib import Path
import shutil
import sys

for source, destination in json.loads(Path(sys.argv[1]).read_text()):
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    output.chmod(0o644)
    os.utime(output, (0, 0))

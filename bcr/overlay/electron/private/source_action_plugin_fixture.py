# SPDX-License-Identifier: MIT
"""Probe a declared Python plugin through the same protocol as build generators."""

import json
import os
from pathlib import Path
import subprocess
import sys

if sys.argv[1] == "generate":
    plugin = Path(__file__).parent / "plugin"
    result = subprocess.run(
        [str(plugin.resolve()), "probe", "two words", "", "caf\u00e9"],
        input=b"request\0body\n",
        stdout=subprocess.PIPE,
        check=True,
    )
    Path(sys.argv[2]).write_bytes(result.stdout)
else:
    from helper import MARKER

    print(json.dumps({
        "arguments": sys.argv[2:],
        "request": sys.stdin.buffer.read().decode(),
        "marker": MARKER,
        "path": os.environ["PATH"],
        "safe_path": sys.flags.safe_path,
        "no_user_site": sys.flags.no_user_site,
        "literal": Path(__file__).with_name("literal 世界.txt").read_text(encoding="utf-8"),
        "empty_literal": (Path(__file__).parents[1] / "third_party/fixture package/.bazel-license-input").read_bytes() == b"",
    }, sort_keys=True))

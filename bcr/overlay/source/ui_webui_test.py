# SPDX-License-Identifier: MIT
"""Execute the real compiled/minified WebUI color module with pinned Node."""

from pathlib import Path
import subprocess
import sys

PROGRAM = """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const bytes = readFileSync(process.argv[1]);
const color = await import('data:text/javascript;base64,' + bytes.toString('base64'));
assert.deepEqual(color.hexColorToSkColor('#1234ab'), {value: 0xff1234ab});
assert.equal(color.skColorToHexColor({value: 0x801234ab}), '#1234ab');
assert.equal(color.skColorToRgba({value: 0x801234ab}), 'rgba(18, 52, 171, 0.50)');
assert.deepEqual(color.hexColorToSkColor('invalid'), {value: 0});
"""

if len(sys.argv) != 3:
    raise ValueError("Expected declared Node and generated module")
result = subprocess.run([str(Path(sys.argv[1]).resolve()), "--input-type=module", "-e", PROGRAM, "--", str(Path(sys.argv[2]).resolve())], env={"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "NODE_PATH": "", "NODE_OPTIONS": ""})
if result.returncode:
    print("check failed: ui_webui generated module semantics", file=sys.stderr)
    raise SystemExit(result.returncode)

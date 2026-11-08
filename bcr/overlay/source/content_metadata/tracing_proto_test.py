# SPDX-License-Identifier: MIT
"""Exercise real protoc/ts-proto output through its generated wire API."""

from pathlib import Path
import subprocess
import sys

PROGRAM = """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const bytes = readFileSync(process.argv[1]);
const {TraceConfig} = await import('data:text/javascript;base64,' + bytes.toString('base64'));
const config = TraceConfig.fromPartial({durationMs: 250});
assert.deepEqual([...TraceConfig.encode(config).finish()], [24, 250, 1]);
const nested = TraceConfig.fromPartial({durationMs: 250, buffers: [{sizeKb: 1024}]});
const decoded = TraceConfig.decode(TraceConfig.encode(nested).finish());
assert.equal(decoded.durationMs, 250);
assert.equal(decoded.buffers.length, 1);
assert.equal(decoded.buffers[0].sizeKb, 1024);
assert.throws(() => TraceConfig.decode(Uint8Array.of(0x80)));
"""

if len(sys.argv) != 3:
    raise ValueError("Expected declared Node and bundled tracing module")
result = subprocess.run([
    str(Path(sys.argv[1]).resolve()), "--input-type=module", "-e", PROGRAM,
    "--", str(Path(sys.argv[2]).resolve()),
], env={"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "NODE_PATH": "", "NODE_OPTIONS": ""})
if result.returncode:
    print("check failed: tracing_proto generated wire semantics", file=sys.stderr)
    raise SystemExit(result.returncode)

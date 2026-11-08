# SPDX-License-Identifier: MIT
"""Exercise original Mojo bundle and compressed DevTools resource products."""

from pathlib import Path
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ElementTree

NODE, LITE, GRD, HTML, COMPRESSED, DIGEST = map(Path, sys.argv[1:])
del sys.argv[1:]

WIRE_PROGRAM = """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const context = vm.createContext({TextEncoder, TextDecoder});
context.self = context;
new vm.Script(readFileSync(process.argv[1], 'utf8')).runInContext(context);
const wire = context.mojo.internal;
const buffer = new ArrayBuffer(16);
const view = new DataView(buffer);
wire.setUint64(view, 0, 0xfedcba9876543210n);
assert.equal(wire.getUint64(view, 0), 0xfedcba9876543210n);
assert.equal(view.getBigUint64(0, wire.kHostLittleEndian), 0xfedcba9876543210n);
wire.setInt64(view, 8, -9007199254740993n);
assert.equal(wire.getInt64(view, 8), -9007199254740993n);
assert.equal(view.getBigInt64(8, wire.kHostLittleEndian), -9007199254740993n);
assert.equal(wire.align(17, 8), 24);
"""

BROTLI_PROGRAM = """
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {brotliDecompressSync} from 'node:zlib';
import {createHash} from 'node:crypto';
const [source, compressed, digest] = process.argv.slice(1).map(path => readFileSync(path));
assert.deepEqual([...compressed.subarray(0, 2)], [0x1e, 0x9b]);
assert.equal(compressed.readUIntLE(2, 6), source.length);
assert.deepEqual(brotliDecompressSync(compressed.subarray(8)), source);
assert.equal(digest.toString('utf8').trim(), createHash('sha1').update(source).digest('hex'));
"""


def run_node(program, *inputs):
    subprocess.run([
        str(NODE.resolve()), "--input-type=module", "-e", program, "--",
        *(str(path.resolve()) for path in inputs),
    ], check=True, env={"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "NODE_PATH": "", "NODE_OPTIONS": ""})


class WebAssetsTest(unittest.TestCase):
    def test_mojo_lite_preserves_signed_unsigned_wire_values(self):
        run_node(WIRE_PROGRAM, LITE)

    def test_devtools_brotli_payload_and_hash_match_original_html(self):
        run_node(BROTLI_PROGRAM, HTML, COMPRESSED, DIGEST)

    def test_manifest_points_to_compressed_frontend_assets(self):
        nodes = list(ElementTree.parse(GRD).iter("include"))
        protocol = [node for node in nodes if node.attrib["name"] == "COMPRESSED_PROTOCOL_JSON"]
        self.assertEqual(len(protocol), 1)
        self.assertEqual(protocol[0].attrib["file"], "${protocol_file}")
        self.assertEqual(protocol[0].attrib["compress"], "brotli")
        self.assertEqual(protocol[0].attrib["skip_in_resource_map"], "true")
        includes = {node.attrib["resource_path"]: node.attrib for node in nodes if node is not protocol[0]}
        for resource in ["devtools_app.html", "Images/account-tree.svg"]:
            with self.subTest(resource=resource):
                self.assertEqual(includes[resource]["file"], resource + ".compressed")
                self.assertEqual(includes[resource]["type"], "BINDATA")
                self.assertEqual(includes[resource]["compress"], "false")


if __name__ == "__main__":
    unittest.main()

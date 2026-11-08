# SPDX-License-Identifier: MIT
"""Check the original default-app ASAR preserves compiled code and pinned assets."""

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest

ARCHIVE, NODE = map(Path, sys.argv[1:3])
FILES = dict(zip(sys.argv[3::2], map(Path, sys.argv[4::2])))
del sys.argv[1:]


class DefaultAppAssets(unittest.TestCase):
    def test_original_asar_preserves_every_declared_file_and_integrity(self):
        data = ARCHIVE.read_bytes()
        self.assertGreater(len(data), 16)
        size_pickle, header_size, header_pickle, json_size = struct.unpack_from("<IIII", data)
        self.assertEqual(size_pickle, 4)
        self.assertEqual(header_pickle + 4, header_size)
        self.assertLessEqual(json_size + 8, header_size)
        header = json.loads(data[16:16 + json_size])
        body = 8 + header_size
        found = {}
        pending = [("", header)]
        while pending:
            prefix, directory = pending.pop()
            for name, entry in directory["files"].items():
                path = prefix + name
                if "files" in entry:
                    pending.append((path + "/", entry))
                else:
                    found[path] = entry
        self.assertEqual(set(found), set(FILES))
        for name, original in FILES.items():
            with self.subTest(file=name):
                entry = found[name]
                self.assertNotIn("link", entry)
                self.assertFalse(entry.get("unpacked", False))
                offset = body + int(entry["offset"])
                self.assertLessEqual(offset + entry["size"], len(data))
                payload = data[offset:offset + entry["size"]]
                self.assertEqual(payload, original.read_bytes())
                integrity = entry["integrity"]
                self.assertEqual(integrity["algorithm"], "SHA256")
                self.assertEqual(hashlib.sha256(payload).hexdigest(), integrity["hash"])
                block_size = integrity["blockSize"]
                self.assertGreater(block_size, 0)
                blocks = [hashlib.sha256(payload[index:index + block_size]).hexdigest() for index in range(0, len(payload), block_size)]
                self.assertEqual(blocks, integrity["blocks"])
                if name.endswith(".js"):
                    subprocess.run([str(NODE.resolve()), "--input-type=module", "--check"], input=payload, check=True,
                                   env={"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"})


if __name__ == "__main__":
    unittest.main()

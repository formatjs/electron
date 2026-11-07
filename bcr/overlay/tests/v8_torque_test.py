# SPDX-License-Identifier: MIT
"""Exercise complete captured Torque generation and its malformed-input boundary."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MANIFEST = Path(sys.argv[1])
TOOL = str(Path(sys.argv[2]).absolute())
GRAPH = Path(sys.argv[3])
del sys.argv[1:]


class V8TorqueTest(unittest.TestCase):
    def test_complete_engine_interfaces_and_reproducibility(self):
        report = json.loads(MANIFEST.read_text())
        self.assertEqual(report["source_count"], 246)
        self.assertEqual(report["output_count"], 1250)
        self.assertTrue(report["reproducibility_checked"])
        self.assertEqual(report["profile_sha256"], hashlib.sha256(GRAPH.read_bytes()).hexdigest())
        self.assertEqual(len(report["files"]), report["output_count"])
        for entry in report["files"]:
            data = (MANIFEST.parent / entry["path"]).read_bytes()
            self.assertEqual(len(data), entry["size"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
        declarations = (MANIFEST.parent / "torque-generated/class-forward-declarations.h").read_text()
        for name in ("JSArray", "JSCollator", "JSTemporalPlainDate"):
            self.assertRegex(declarations, r"class\s+" + name + r"\s*;")
        builtins = (MANIFEST.parent / "torque-generated/builtin-definitions.h").read_text()
        self.assertIn("ArrayMap", builtins)

    def test_malformed_torque_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "invalid.tq").write_text("this is not Torque;\n")
            output = root / "generated"
            output.mkdir()
            result = subprocess.run([TOOL, "-o", str(output), "-v8-root", str(root), "invalid.tq"], cwd=root, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()

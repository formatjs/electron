# SPDX-License-Identifier: MIT
"""Validate emitted JS syntax and its lossless native JS2C embedding."""
from pathlib import Path
import re
import subprocess
import sys
import unittest


class ElectronBundlesTest(unittest.TestCase):
    def test_all_bundles_parse_and_embed_losslessly(self):
        node = Path(sys.argv[1]).resolve()
        native = Path(sys.argv[2]).read_text(encoding="utf-8")
        files = {Path(path).stem: Path(path) for path in sys.argv[3:]}
        self.assertEqual(len(files), 8)
        registered = re.findall(r'\{"([^"]+)", UnionBytes\(&', native)
        self.assertEqual(set(registered), {"electron/js2c/" + name for name in files})
        for name, path in files.items():
            with self.subTest(bundle=name):
                subprocess.run([str(node), "--check", str(path)], check=True, capture_output=True, timeout=15)
                match = re.search(r"\*electron_js2c_" + name + r'_raw = .*?R"JS2C1b732aee\((.*?)\)JS2C1b732aee"', native, re.DOTALL)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), path.read_text(encoding="utf-8"))
        self.assertIn("BuiltinLoader::LoadEmbedderJavaScriptSource()", native)
        self.assertIn("StaticExternalOneByteResource", native)
        self.assertIn("StaticExternalTwoByteResource", native)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

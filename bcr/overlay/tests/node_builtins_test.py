# SPDX-License-Identifier: MIT
"""Exercise real Node JS2C output and Electron's original-fs producer together."""
import ast
import json
from pathlib import Path
import re
import sys
import unittest


class NodeBuiltinsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(sys.argv[1]).read_text(encoding="utf-8")
        cls.config = ast.literal_eval(Path(sys.argv[2]).read_text(encoding="utf-8"))

    def payload(self, name):
        match = re.search(r"\*" + re.escape(name) + r'_raw = .*?R"JS2C1b732aee\((.*?)\)JS2C1b732aee"', self.source, re.DOTALL)
        self.assertIsNotNone(match, name)
        return match.group(1)

    def test_original_fs_isolated_without_replacing_normal_fs(self):
        registered = re.findall(r'\{"([^"]+)", UnionBytes\(&', self.source)
        self.assertEqual(len(registered), 370)
        self.assertEqual(len(set(registered)), len(registered))
        for name in ("fs", "original-fs", "fs/promises", "original-fs/promises",
                     "internal/fs/utils", "internal/original-fs/utils",
                     "internal/deps/undici/undici", "internal/deps/v8/tools/tickprocessor"):
            self.assertIn(name, registered)
        normal = self.payload("fs")
        isolated = self.payload("original_fs")
        self.assertIn("require('internal/fs/utils')", normal)
        self.assertIn("require('internal/original-fs/utils')", isolated)
        self.assertNotIn("require('fs", isolated)
        self.assertNotIn("internal/fs/", isolated)
        self.assertIn("require('internal/original-fs/promises')", self.payload("original_fs_promises"))
        self.assertIn("BuiltinLoader::LoadJavaScriptSource()", self.source)
        self.assertNotIn("BuiltinLoader::LoadEmbedderJavaScriptSource()", self.source)

    def test_target_config_embedded_as_json(self):
        embedded = json.loads(self.payload("config"))
        self.assertEqual(embedded["target_defaults"]["default_configuration"], "Release")
        variables = embedded["variables"]
        self.assertEqual(variables["node_module_version"], 140)
        self.assertEqual(variables["napi_build_version"], "10")
        self.assertEqual(variables["shlib_suffix"], "so")
        self.assertEqual(variables["v8_enable_sandbox"], 1)
        self.assertEqual(variables["v8_enable_pointer_compression"], 1)
        self.assertIs(variables["node_use_node_snapshot"], False)
        self.assertIs(variables["node_use_openssl"], True)
        self.assertEqual(self.config["variables"]["node_module_version"], variables["node_module_version"])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

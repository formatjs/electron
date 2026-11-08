# SPDX-License-Identifier: MIT
"""Exercise generator plugins through the declared native execution tool."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import source_action

LAUNCHER = str(Path(sys.argv.pop(1)).resolve())
GENERATED = Path(sys.argv.pop(1))


class SourceActionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="source plugin test ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = Path(__file__).parent
        scripts = {
            "scripts/fixture.py": (source / "source_action_plugin_fixture.py").read_text(),
            "scripts/helper.py": (source / "source_action_plugin_helper.py").read_text(),
            "scripts/literal 世界.txt": "Declared literal 世界.\n",
            "third_party/fixture package/.bazel-license-input": "",
        }
        inputs = []
        for logical, content in scripts.items():
            actual = self.root / logical
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_text(content)
            inputs.append([str(actual), logical])
        self.output = self.root / "result.json"
        self.manifest = {
            "inputs": inputs,
            "outputs": [[str(self.output), "result.json"]],
            "tools": [],
            "script": "scripts/fixture.py",
            "args": ["generate", "result.json"],
            "response": [],
            "environment": {},
            "verify_reproducible": True,
            "python_launcher": LAUNCHER,
            "python_tools": {"scripts/plugin": "scripts/fixture.py"},
        }

    def test_plugin_exec_preserves_protocol_arguments_and_isolation(self):
        source_action.run(self.manifest)
        expected = {
            "arguments": ["two words", "", "caf\u00e9"],
            "request": "request\0body\n",
            "marker": "declared sibling import",
            "path": "",
            "safe_path": True,
            "no_user_site": 1,
            "literal": "Declared literal 世界.\n",
            "empty_literal": True,
        }
        self.assertEqual(json.loads(self.output.read_text()), expected)
        self.assertEqual(json.loads(GENERATED.read_text()), expected)

    def test_plugin_cannot_replace_inputs_or_execute_undeclared_script(self):
        cases = [
            ({"out//bazel-import/result.json": "scripts/fixture.py"}, "path must be normalized"),
            ({"out/bazel-import/result.json": "scripts/fixture.py"}, "cannot replace generator outputs"),
            ({"scripts/plugin": "scripts/missing.py"}, "not a declared input"),
            ({"scripts/fixture.py": "scripts/fixture.py"}, "conflicts with a declared input"),
            ({"scripts/helper": "scripts/fixture.py"}, "conflicts with a declared input"),
        ]
        # The argument file has the same collision rules as the executable.
        self.manifest["inputs"].append([self.manifest["inputs"][0][0], "scripts/helper.argv"])
        for tools, error in cases:
            with self.subTest(tools=tools):
                self.manifest["python_tools"] = tools
                with self.assertRaisesRegex(ValueError, error):
                    source_action.run(self.manifest)
                self.assertFalse(self.output.exists())

    def test_native_launcher_rejects_truncated_argument_file(self):
        executable = self.root / "broken plugin"
        executable.symlink_to(LAUNCHER)
        executable.with_name(executable.name + ".argv").write_bytes(b"unterminated")
        result = subprocess.run([str(executable)], capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, b"Python plugin launcher: invalid argument file\n")


if __name__ == "__main__":
    unittest.main()

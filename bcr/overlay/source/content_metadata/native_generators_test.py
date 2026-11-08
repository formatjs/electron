# SPDX-License-Identifier: MIT
"""Compare captured upstream invocations with existing native Bazel producers."""

from pathlib import Path
import sys
import unittest

INPUTS = [Path(value) for value in sys.argv[1:]]
sys.argv[1:] = []
if len(INPUTS) != 8:
    raise ValueError("Expected four declared producer artifact pairs")


class NativeGenerators(unittest.TestCase):
    def test_original_generators_match_bazel_fuse_and_node_artifacts(self):
        for existing, native in zip(INPUTS[::2], INPUTS[1::2]):
            with self.subTest(artifact=native.name):
                self.assertEqual(existing.name, native.name)
                self.assertEqual(existing.read_bytes(), native.read_bytes())


if __name__ == "__main__":
    unittest.main()

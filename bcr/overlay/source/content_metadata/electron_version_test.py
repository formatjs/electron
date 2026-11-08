# SPDX-License-Identifier: MIT
"""Check original Electron version producers across native and Windows metadata."""

import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

INPUTS = [Path(value) for value in sys.argv[1:]]
del sys.argv[1:]
if len(INPUTS) != 8:
    raise ValueError("Expected stable/beta artifacts and original lock metadata")


class ElectronVersion(unittest.TestCase):
    def test_stable_and_beta_metadata_preserve_semver_and_windows_versions(self):
        cases = [
            (INPUTS[:3], dict(full_version="39.0.0", major=39, minor=0, patch=0,
                            prerelease="", prerelease_number="0", has_prerelease=0)),
            (INPUTS[3:6], dict(full_version="40.2.1-beta.3", major=40, minor=2, patch=1,
                             prerelease="beta.3", prerelease_number=3, has_prerelease=1)),
        ]
        for (arguments, header, resource), expected in cases:
            with self.subTest(version=expected["full_version"]):
                self.assertEqual(json.loads(arguments.read_text()), expected)
                macros = dict(re.findall(r"^#define (ELECTRON_[A-Z_]+) (.+)$", header.read_text(), re.M))
                for name in ("MAJOR", "MINOR", "PATCH"):
                    self.assertEqual(macros["ELECTRON_" + name + "_VERSION"], str(expected[name.lower()]))
                self.assertIn("#if " + str(expected["has_prerelease"]), header.read_text())
                if expected["has_prerelease"]:
                    self.assertEqual(macros["ELECTRON_PRE_RELEASE_VERSION"], "-beta.3")
                    self.assertIn('"40.2.1-beta.3"', header.read_text())
                versions = re.findall(r"^\s*(?:FILEVERSION|PRODUCTVERSION) ([0-9,]+)$", resource.read_text(), re.M)
                self.assertEqual(versions, ["39,0,0,0"] * 2 if not expected["has_prerelease"] else ["40,2,1,3"] * 2)
                self.assertNotIn("$", header.read_text() + resource.read_text())

    def test_node_tool_pin_matches_original_yarn_lock(self):
        lock = json.loads(INPUTS[7].read_text())
        self.assertEqual(hashlib.sha256(INPUTS[6].read_bytes()).hexdigest(), lock["yarn_lock_sha256"])
        semver = lock["packages"][lock["roots"]["semver"]]
        self.assertEqual((semver["name"], semver["version"], semver["dependencies"]), ("semver", "7.6.3", {}))


if __name__ == "__main__":
    unittest.main()

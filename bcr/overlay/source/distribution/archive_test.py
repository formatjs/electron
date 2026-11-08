# SPDX-License-Identifier: MIT
"""Exercise real ELF relocation, transitive loading and closed dependency checks."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from electron.private.runtime_archive import assemble

ARCHIVE, REPORT, PATCHELF, PROGRAM, ANSWER, BASE = map(Path, sys.argv[1:])
del sys.argv[1:]


class RuntimeArchiveTest(unittest.TestCase):
    def manifest(self):
        return {
            "entries": [
                {"source": str(PROGRAM), "path": "electron", "library": False},
                {"source": str(ANSWER), "path": "lib/libfixture_answer.so", "library": True},
                {"source": str(BASE), "path": "lib/libfixture_base.so", "library": True},
            ],
            "executables": ["electron"],
            "host_abi": json.loads(REPORT.read_text())["host_abi"],
            "patchelf": str(PATCHELF),
        }

    def test_action_archive_loads_transitive_library_after_relocation(self):
        with tempfile.TemporaryDirectory(prefix="relocated runtime 世界 ") as directory:
            root = Path(directory)
            with zipfile.ZipFile(ARCHIVE) as archive:
                self.assertEqual(archive.namelist(), ["electron", "lib/libfixture_answer.so", "lib/libfixture_base.so"])
                for info in archive.infolist():
                    self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                    target = root / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod((info.external_attr >> 16) & 0o777)
            result = subprocess.run([str(root / "electron")], cwd=root,
                                    env={"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            records = {entry["path"]: entry for entry in json.loads(REPORT.read_text())["elf"]}
            self.assertIn("libfixture_base.so", records["lib/libfixture_answer.so"]["needed"])
            self.assertEqual(records["electron"]["rpath"], "$ORIGIN:$ORIGIN/lib")
            self.assertEqual(records["lib/libfixture_answer.so"]["rpath"], "$ORIGIN:$ORIGIN/..")

    def test_missing_transitive_library_is_rejected_without_host_lookup(self):
        manifest = self.manifest()
        manifest["entries"].pop()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Unbundled runtime dependencies: libfixture_base.so"):
                assemble(manifest, Path(directory))

    def test_mismatched_library_soname_is_rejected(self):
        manifest = self.manifest()
        manifest["entries"][-1]["path"] = "lib/wrong.so"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Runtime SONAME differs from destination: lib/wrong.so"):
                assemble(manifest, Path(directory))


if __name__ == "__main__":
    unittest.main()

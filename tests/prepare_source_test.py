# SPDX-License-Identifier: MIT
import json
import tempfile
import unittest
from pathlib import Path

from tools.prepare_source import prepare


class PrepareSourceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = {name: self.root / name for name in ("chromium", "electron", "node", "v8", "deps_cache", "destination")}
        for name, path in self.paths.items():
            if name != "destination":
                path.mkdir()
        for name in ("chromium", "deps_cache"):
            (self.paths[name] / "DEPS").write_text("matching revisions")
        for group, revision, count in (("chromium", "7efca501bfcc84657ba2921a852e98ce1fb37641", 144), ("v8", "bb294624702efbb17691b642333f06bf5108e600", 1)):
            (self.paths[group] / "electron_patches.json").write_text(json.dumps({"upstream_revision": revision, "patches": ["patch"] * count}))
        core = self.paths["chromium"]
        (core / "build/util").mkdir(parents=True)
        (core / "build/util/LASTCHANGE").write_text("original immutable source")
        (core / "VERSION").write_text("52")
        cache = self.paths["deps_cache"]
        (cache / "VERSION").write_text("59")
        (cache / "third_party/extra").mkdir(parents=True)
        (cache / "third_party/extra/value").write_text("dependency")
        (cache / "out").mkdir()
        (cache / "out/stale.ninja").write_text("stale")

    def test_pinned_sources_win_cache_stays_immutable(self):
        prepare(**self.paths)
        destination = self.paths["destination"]
        self.assertEqual((destination / "VERSION").read_text(), "52")
        self.assertEqual((destination / "third_party/extra/value").read_text(), "dependency")
        self.assertFalse((destination / "out").exists())
        self.assertIn("7efca501", (destination / "build/util/LASTCHANGE").read_text())
        self.assertFalse((destination / "build/util/LASTCHANGE").is_symlink())
        self.assertEqual((self.paths["chromium"] / "build/util/LASTCHANGE").read_text(), "original immutable source")
        self.assertEqual((self.paths["deps_cache"] / "VERSION").read_text(), "59")
        self.assertEqual((destination / "v8").resolve(), self.paths["v8"])

    def test_mismatched_cache_rejected_before_writes(self):
        (self.paths["deps_cache"] / "DEPS").write_text("wrong revisions")
        with self.assertRaisesRegex(ValueError, "DEPS differs"):
            prepare(**self.paths)
        self.assertFalse(self.paths["destination"].exists())

    def test_existing_destination_preserved(self):
        self.paths["destination"].mkdir()
        keep = self.paths["destination"] / "keep"
        keep.write_text("user work")
        with self.assertRaises(FileExistsError):
            prepare(**self.paths)
        self.assertEqual(keep.read_text(), "user work")


if __name__ == "__main__":
    unittest.main()

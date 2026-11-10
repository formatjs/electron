# SPDX-License-Identifier: MIT
import json
import hashlib
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

    def test_declared_only_mode_never_reads_fallback_checkout(self):
        dependency = self.root / 'declared_dependency'
        dependency.mkdir()
        (dependency / 'public.h').write_text('pinned dependency')
        # A cache exists beside the inputs, but was not supplied.
        (self.paths['deps_cache'] / 'DEPS').write_text('wrong revisions')
        arguments = {name: path for name, path in self.paths.items() if name != 'deps_cache'}
        prepare(**arguments, deps_cache=None, dependencies=[('third_party/declared', dependency)])
        destination = self.paths['destination']
        self.assertEqual((destination / 'VERSION').read_text(), '52')
        self.assertEqual((destination / 'third_party/declared/public.h').read_text(), 'pinned dependency')
        self.assertFalse((destination / 'third_party/extra').exists())
        self.assertFalse((destination / 'out').exists())
        provenance = json.loads((destination / 'electron-source-provenance.json').read_text())
        self.assertEqual(provenance['dependency_mode'], 'declared-only')
        self.assertIsNone(provenance['deps_cache'])
        self.assertEqual((self.paths['chromium'] / 'build/util/LASTCHANGE').read_text(), 'original immutable source')

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

    def test_nested_dependency_replaces_private_parents(self):
        squirrel = self.root / "squirrel"
        (squirrel / "vendor/Mantle").mkdir(parents=True)
        original = squirrel / "vendor/Mantle/value.h"
        original.write_text("original")
        mantle = self.root / "mantle"
        mantle.mkdir()
        (mantle / "value.h").write_text("patched")
        prepare(**self.paths, dependencies=[("third_party/squirrel.mac", squirrel), ("third_party/squirrel.mac/vendor/Mantle", mantle)])
        target = self.paths["destination"] / "third_party/squirrel.mac"
        self.assertFalse(target.is_symlink())
        self.assertFalse((target / "vendor").is_symlink())
        self.assertEqual((target / "vendor/Mantle/value.h").read_text(), "patched")
        self.assertEqual(original.read_text(), "original")

    def test_fingerprint_mismatch_rejected_before_writes(self):
        fingerprints = {"chromium": {"source_path": "", "files": {"VERSION": hashlib.sha256(b"different").hexdigest()}}}
        with self.assertRaisesRegex(ValueError, "Patched file differs"):
            prepare(**self.paths, fingerprints=fingerprints)
        self.assertFalse(self.paths["destination"].exists())


if __name__ == "__main__":
    unittest.main()

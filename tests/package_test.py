# SPDX-License-Identifier: MIT
import json
import os
import plistlib
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from electron.private.package import archive_info, package


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.main = self.root / "main.js"
        self.main.write_text("console.log('hello')")
        self.metadata = self.root / "package.json"
        self.metadata.write_text(json.dumps({"name": "test", "main": "main.js", "version": "1.0.0"}))
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({"package.json": str(self.metadata), "main.js": str(self.main)}))

    def runtime(self, files):
        archive = self.root / "runtime.zip"
        with zipfile.ZipFile(archive, "w") as writer:
            for name, value, mode in files:
                writer.writestr(archive_info(name, mode), value)
        return archive

    def build(self, runtime, platform="linux_amd64", filename="app.zip"):
        output = self.root / filename
        package(runtime, platform, self.manifest, output, "Hello", "org.example.hello")
        return output

    def test_linux_layout_modes_licenses_determinism(self):
        runtime = self.runtime([("electron", b"ELF", stat.S_IFREG | 0o755), ("LICENSE", b"upstream notice", stat.S_IFREG | 0o644), ("resources/default_app.asar", b"default", stat.S_IFREG | 0o644)])
        first = self.build(runtime)
        os.chmod(self.main, 0o600)
        os.utime(self.main, (123456, 123456))
        second = self.build(runtime, filename="again.zip")
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as result:
            self.assertEqual(result.read("Hello"), b"ELF")
            self.assertEqual(result.getinfo("Hello").external_attr >> 16, stat.S_IFREG | 0o755)
            self.assertEqual(result.read("LICENSE"), b"upstream notice")
            self.assertEqual(result.read("resources/app/main.js"), self.main.read_bytes())
            self.assertNotIn("resources/default_app.asar", result.namelist())

    def test_windows_renames_crash_handler(self):
        runtime = self.runtime([("electron.exe", b"PE", stat.S_IFREG | 0o644), ("electron_wer.dll", b"WER", stat.S_IFREG | 0o644)])
        with zipfile.ZipFile(self.build(runtime, "windows_arm64")) as result:
            self.assertEqual(result.read("Hello_wer.dll"), b"WER")
            self.assertEqual(result.read("Hello.exe"), b"PE")

    def test_macos_plist_and_framework_symlinks(self):
        base = "Electron.app/Contents/"
        runtime = self.runtime([(base + "MacOS/Electron", b"MachO", stat.S_IFREG | 0o755), (base + "Info.plist", plistlib.dumps({"CFBundleIdentifier": "com.github.Electron"}), stat.S_IFREG | 0o644), (base + "Frameworks/F.framework/F", b"Versions/Current/F", stat.S_IFLNK | 0o777), (base + "_CodeSignature/CodeResources", b"invalidated", stat.S_IFREG | 0o644)])
        with zipfile.ZipFile(self.build(runtime, "darwin_arm64")) as result:
            values = plistlib.loads(result.read("Hello.app/Contents/Info.plist"))
            self.assertEqual(values["CFBundleExecutable"], "Hello")
            self.assertEqual(values["CFBundleIdentifier"], "org.example.hello")
            self.assertEqual(result.read("Hello.app/Contents/Frameworks/F.framework/F"), b"Versions/Current/F")
            self.assertTrue(stat.S_ISLNK(result.getinfo("Hello.app/Contents/Frameworks/F.framework/F").external_attr >> 16))
            self.assertFalse(any("_CodeSignature" in name for name in result.namelist()))

    def test_rejects_unsafe_paths_links_collisions(self):
        for name, data, mode, platform in [("../escape", b"x", stat.S_IFREG, "linux_amd64"), ("link", b"../../outside", stat.S_IFLNK, "linux_amd64"), ("resources/app/main.js", b"x", stat.S_IFREG, "linux_amd64"), ("hello", b"duplicate executable", stat.S_IFREG, "windows_amd64")]:
            with self.subTest(name=name):
                main = "electron.exe" if platform.startswith("windows") else "electron"
                runtime = self.runtime([(main, b"binary", stat.S_IFREG | 0o755), (name if name != "hello" else "HELLO.exe", data, mode)])
                with self.assertRaises(ValueError):
                    self.build(runtime, platform)

    def test_rejects_symlink_parent_of_app(self):
        runtime = self.runtime([("electron", b"binary", stat.S_IFREG | 0o755), ("resources", b"elsewhere", stat.S_IFLNK | 0o777)])
        with self.assertRaisesRegex(ValueError, "file/directory collision"):
            self.build(runtime)

    def test_generated_app_and_dependency_trees(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        (bundle / "main.js").write_text("require('dependency')")
        dependencies = self.root / "dependencies"
        (dependencies / "dependency").mkdir(parents=True)
        (dependencies / "dependency/index.js").write_text("module.exports = 42")
        self.metadata.write_text(json.dumps({"main": "dist/main.js"}))
        self.manifest.write_text(json.dumps({"package.json": str(self.metadata), "dist": str(bundle), "node_modules": str(dependencies)}))
        runtime = self.runtime([("electron", b"binary", stat.S_IFREG | 0o755)])
        with zipfile.ZipFile(self.build(runtime)) as result:
            self.assertEqual(result.read("resources/app/dist/main.js"), b"require('dependency')")
            self.assertEqual(result.read("resources/app/node_modules/dependency/index.js"), b"module.exports = 42")
        # Local Bazel sandboxes stage declared tree files as symlinks.
        (bundle / "staged.js").symlink_to(self.main)
        with zipfile.ZipFile(self.build(runtime)) as result:
            self.assertEqual(result.read("resources/app/dist/staged.js"), self.main.read_bytes())
        (bundle / "outside_directory").symlink_to(dependencies, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "materialized dependencies"):
            self.build(runtime)


if __name__ == "__main__":
    unittest.main()

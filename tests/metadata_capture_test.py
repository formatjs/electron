"""Pinned Rust component composition and exact source repository discovery."""

from pathlib import Path
import tempfile
import unittest

from capture_linux_metadata import repository, rust_sysroot


class MetadataCaptureTest(unittest.TestCase):
    def components(self, root):
        for component, paths in {
            'rustc': ['bin/rustc', 'lib/compiler.so'],
            'rust_std_x64': ['lib/rustlib/x86_64-unknown-linux-gnu/lib/libstd.rlib'],
            'rust_std_arm64': ['lib/rustlib/aarch64-unknown-linux-gnu/lib/libstd.rlib'],
        }.items():
            for relative in paths:
                path = root / component / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((component + ':' + relative).encode())

    def test_union_keeps_both_cpus_and_compiler_location_without_mutating_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            inputs, output = Path(temporary) / 'inputs', Path(temporary) / 'rust'
            self.components(inputs)
            originals = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in inputs.rglob('*') if path.is_file()}
            (inputs / 'rustc/lib/alias.so').symlink_to('compiler.so')
            rust_sysroot(inputs, output)
            self.assertFalse((output / 'bin/rustc').is_symlink())
            self.assertEqual((output / 'bin/rustc').read_bytes(), (inputs / 'rustc/bin/rustc').read_bytes())
            for architecture in ('x86_64', 'aarch64'):
                self.assertTrue((output / ('lib/rustlib/' + architecture + '-unknown-linux-gnu/lib/libstd.rlib')).is_file())
            self.assertEqual((output / 'lib/alias.so').read_bytes(), (inputs / 'rustc/lib/compiler.so').read_bytes())
            for path, (content, mtime) in originals.items():
                self.assertEqual(path.read_bytes(), content)
                self.assertEqual(path.stat().st_mtime_ns, mtime)

    def test_shared_file_disagreement_and_external_links_are_rejected(self):
        for kind in ('conflict', 'external-link', 'directory-link'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                inputs = Path(temporary) / 'inputs'
                self.components(inputs)
                if kind == 'conflict':
                    (inputs / 'rust_std_x64/lib/compiler.so').write_bytes(b'different bytes')
                elif kind == 'external-link':
                    outside = Path(temporary) / 'outside'
                    outside.write_bytes(b'private input')
                    (inputs / 'rustc/lib/link.so').symlink_to(outside)
                else:
                    (inputs / 'rustc/lib/directory-link').symlink_to(inputs / 'rustc/bin', target_is_directory=True)
                with self.assertRaises(ValueError):
                    rust_sysroot(inputs, Path(temporary) / 'rust')

    def test_repository_lookup_rejects_ambiguity_and_never_searches_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root / 'electron++sources+electron_node_sources'
            expected.mkdir()
            self.assertEqual(repository(root, 'electron_node_sources'), expected)
            with self.assertRaises(ValueError):
                repository(root, 'missing_sources')
            (root / 'other++sources+electron_node_sources').mkdir()
            with self.assertRaises(ValueError):
                repository(root, 'electron_node_sources')


if __name__ == '__main__':
    unittest.main()

# SPDX-License-Identifier: MIT
import unittest
from pathlib import Path
import tempfile

from tools.capture_gn_edges import dependency_kinds, split_dependencies, private_config


class GnDependenciesTest(unittest.TestCase):
    def test_instrumentation_never_writes_source_symlink_target_and_restores_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'pinned-source.gn'
            source.write_bytes(b'original pinned bytes')
            config = root / 'BUILDCONFIG.gn'
            config.symlink_to('pinned-source.gn')
            original = source.stat()
            with self.assertRaisesRegex(RuntimeError, 'capture failed'):
                with private_config(config) as content:
                    self.assertEqual(content, b'original pinned bytes')
                    config.write_bytes(b'instrumented private bytes')
                    self.assertEqual(source.read_bytes(), content)
                    raise RuntimeError('capture failed')
            self.assertTrue(config.is_symlink())
            self.assertEqual(config.readlink(), Path('pinned-source.gn'))
            self.assertEqual(source.read_bytes(), b'original pinned bytes')
            self.assertEqual(source.stat().st_mtime_ns, original.st_mtime_ns)
            self.assertEqual(list(root.glob('.gn-edges-*')), [])

    def test_regular_private_config_restores_original_node(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'BUILDCONFIG.gn'
            config.write_bytes(b'original')
            original = config.stat()
            with private_config(config):
                config.write_bytes(b'instrumented')
            self.assertEqual(config.read_bytes(), b'original')
            self.assertEqual(config.stat().st_ino, original.st_ino)
            self.assertEqual(config.stat().st_mtime_ns, original.st_mtime_ns)

    def graph(self):
        toolchain = '//build/toolchain/linux:clang_x64'
        labels = ['//app:app', '//lib:library', '//lib:driver']
        targets = {label: dict(toolchain=toolchain, deps=[], metadata=dict(bazel_private_deps=[], bazel_public_deps=[], bazel_data_deps=[])) for label in labels}
        targets['//app:app'].update(deps=labels[1:], metadata=dict(
            bazel_private_deps=[],
            bazel_public_deps=[labels[1] + '(' + toolchain + ')'],
            bazel_data_deps=[label + '(' + toolchain + ')' for label in labels[1:]],
        ))
        return dict(targets=targets)

    def test_runtime_driver_never_becomes_link_dependency(self):
        graph = self.graph()
        capture = dict(targets=dependency_kinds(graph))
        self.assertEqual(split_dependencies('//app:app', graph['targets']['//app:app']['deps'], capture),
                         dict(gn_link_deps=['//lib:library'], gn_data_deps=['//lib:driver']))

    def test_incomplete_gn_metadata_rejected(self):
        graph = self.graph()
        graph['targets']['//app:app']['metadata']['bazel_data_deps'] = []
        with self.assertRaisesRegex(ValueError, 'differs from GN graph'):
            dependency_kinds(graph)

    def test_capture_from_different_graph_rejected(self):
        capture = dict(targets=dependency_kinds(self.graph()))
        with self.assertRaisesRegex(ValueError, 'do not match source graph'):
            split_dependencies('//app:app', ['//lib:library'], capture)


if __name__ == '__main__':
    unittest.main()

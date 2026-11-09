# SPDX-License-Identifier: MIT
import unittest

from tools.capture_gn_edges import dependency_kinds, split_dependencies


class GnDependenciesTest(unittest.TestCase):
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

"""Runtime/compiler capture preserves compiler roles and Protobuf safety flags."""

import copy
from pathlib import Path
import tempfile
import unittest

from capture_protobuf import ABSEIL, JS, JS_REVISION, PREFIX, capture
from capture_target import builtins_archive


class ProtobufCaptureTest(unittest.TestCase):
    def fixture(self, temporary, architecture):
        root = Path(temporary)
        chromium, javascript = root / 'chromium', root / 'javascript'
        (chromium / 'third_party/protobuf').mkdir(parents=True)
        javascript.mkdir()
        (chromium / 'third_party/protobuf/README.chromium').write_text('Version: 32.0\n')
        (chromium / 'DEPS').write_text("'/external/github.com/protocolbuffers/protobuf-javascript' + '@' + '" + JS_REVISION + "'")
        for directory in (chromium / 'third_party/protobuf', javascript):
            (directory / 'unit.cc').write_text('original source')
            (directory / 'public.h').write_text('original header')
        chains = {'target': 'clang_' + architecture, 'execution': 'clang_x64',
                  'snapshot': 'clang_x64_v8_arm64' if architecture == 'arm64' else 'clang_x64'}
        def label(bare, role):
            return bare + ('' if chains[role] == chains['target'] else '(//build/toolchain/linux:' + chains[role] + ')')
        targets = {}
        safety = ['GOOGLE_PROTOBUF_NO_RTTI', 'PROTOBUF_INTERNAL_BOUNDS_CHECK_MODE_ABORT']
        for role, chain in chains.items():
            cpu = architecture if role == 'target' else 'x64'
            aggregate = label('//third_party/abseil-cpp:absl_component_deps', role)
            dep = label('//third_party/abseil-cpp/absl/base:base', role)
            targets[dep] = {'type': 'static_library', 'toolchain': '//build/toolchain/linux:' + chain}
            targets[aggregate] = {'type': 'group', 'toolchain': '//build/toolchain/linux:' + chain, 'deps': [dep]}
            targets[label(ABSEIL, role)] = {'type': 'group', 'toolchain': '//build/toolchain/linux:' + chain, 'deps': [aggregate]}
            for name in ('utf8_range', 'protobuf_lite'):
                targets[label(PREFIX + name, role)] = {'type': 'static_library', 'toolchain': '//build/toolchain/linux:' + chain,
                     'sources': ['//third_party/protobuf/unit.cc'], 'defines': [] if name == 'utf8_range' else safety,
                     'libs': [builtins_archive(cpu)], 'deps': [] if name == 'utf8_range' else [label(PREFIX + 'utf8_range', role), label(ABSEIL, role)]}
            if cpu == 'x64' and chain == 'clang_x64':
                targets[label(JS, role)] = {'type': 'executable', 'toolchain': '//build/toolchain/linux:clang_x64',
                    'sources': ['//third_party/protobuf-javascript/src/unit.cc'], 'defines': safety, 'deps': []}
                targets[label(PREFIX + 'protoc', role)] = {'type': 'executable', 'toolchain': '//build/toolchain/linux:clang_x64',
                    'sources': ['//third_party/protobuf/unit.cc'], 'defines': safety, 'deps': [label(PREFIX + 'protobuf_lite', role), label(JS, role)]}
        return {'target_arch': architecture, 'targets': targets, 'pool': []}, (chromium, javascript), label

    def test_arm_runtime_and_snapshot_never_select_target_protoc(self):
        for architecture in ('x64', 'arm64'):
            with self.subTest(architecture=architecture), tempfile.TemporaryDirectory() as temporary:
                graph, roots, label = self.fixture(temporary, architecture)
                for role in ('target', 'execution', 'snapshot'):
                    result = capture(graph, *roots, architecture, role)
                    compiler = role == 'execution' or architecture == 'x64' and role == 'target'
                    self.assertEqual(result['root'], label(PREFIX + ('protoc' if compiler else 'protobuf_lite'), role))
                    self.assertEqual({v['architecture'] for v in result['libraries'].values()}, {architecture if role == 'target' else 'x64'})
                    lite = result['libraries'][label(PREFIX + 'protobuf_lite', role)]
                    self.assertEqual(lite['name'], 'protobuf_lite')
                    self.assertTrue(lite['abseil'])
                    self.assertEqual(lite['srcs'], ['third_party/protobuf/unit.cc'])
                    self.assertIn(label(PREFIX + 'utf8_range', role), lite['deps'])
                    if compiler:
                        self.assertEqual(result['libraries'][label(JS, role)]['name'], 'protoc_js')
                    if architecture == 'arm64':
                        self.assertIsNone(result['abseil_deps'])
                    elif role == 'target':
                        self.assertEqual(result['abseil_deps'], ['@electron_abseil_sources//absl/base:base'])

    def test_wrong_cpu_runtime_flags_and_dependency_role_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            graph, roots, label = self.fixture(temporary, 'arm64')
            for field, value in [('libs', [builtins_archive('x64')]), ('defines', []),
                                 ('deps', [label(PREFIX + 'utf8_range', 'snapshot')])]:
                invalid = copy.deepcopy(graph)
                invalid['targets'][PREFIX + 'protobuf_lite'][field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    capture(invalid, *roots, 'arm64')
            aggregate = '//third_party/abseil-cpp:absl_component_deps'
            graph['targets'][aggregate]['deps'] = [label('//third_party/abseil-cpp/absl/base:base', 'execution')]
            with self.assertRaisesRegex(ValueError, 'Abseil aggregate crosses compiler role'):
                capture(graph, *roots, 'arm64')


if __name__ == '__main__':
    unittest.main()

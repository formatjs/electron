"""Keep ARM64 libraries and host generators separate through Perfetto capture."""

import copy
from pathlib import Path
import tempfile
import unittest

from capture_perfetto import BUILD, ROOT, capture
from capture_target import builtins_archive


class PerfettoCaptureTest(unittest.TestCase):
    def fixture(self, root, architecture):
        chromium, perfetto, jsoncpp = [root / name for name in ('chromium', 'perfetto', 'jsoncpp')]
        for directory in (chromium, perfetto, jsoncpp):
            directory.mkdir()
        (chromium / 'DEPS').write_text('42e892d96e47b1f6e29844cc705e148ec4856448')
        for name in ('runtime.cc', 'plugin.cc', 'include/public.h', 'gn/write_buildflag_header.py'):
            path = perfetto / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('original source')
        chains = {'target': 'clang_' + architecture, 'execution': 'clang_x64',
                  'snapshot': 'clang_x64_v8_arm64' if architecture == 'arm64' else 'clang_x64'}

        def label(bare, role):
            chain = chains[role]
            return bare + ('(//build/toolchain/linux:' + chain + ')' if chain != chains['target'] else '')

        protoc = label('//third_party/protobuf:protoc', 'execution')
        plugin = label('//third_party/perfetto:plugin', 'execution')
        host_prefix = '' if architecture == 'x64' else 'clang_x64/'
        targets = {protoc: {'type': 'executable', 'toolchain': '//build/toolchain/linux:clang_x64',
                            'outputs': [BUILD + host_prefix + 'protoc']},
                   plugin: {'type': 'executable', 'toolchain': '//build/toolchain/linux:clang_x64',
                            'outputs': [BUILD + host_prefix + 'plugin'],
                            'sources': ['//third_party/perfetto/plugin.cc'], 'deps': [protoc]}}
        for role, chain in chains.items():
            prefix = '' if chain == chains['target'] else chain + '/'
            cpu = architecture if role == 'target' else 'x64'
            library = label(ROOT, role)
            action = label('//third_party/perfetto:generate', role)
            zlib = label('//third_party/zlib:zlib', role)
            targets[zlib] = {'type': 'static_library', 'toolchain': '//build/toolchain/linux:' + chain}
            targets[action] = {'type': 'action', 'toolchain': '//build/toolchain/linux:' + chain,
                               'script': '//third_party/perfetto/gn/write_buildflag_header.py',
                               'inputs': [BUILD + host_prefix + 'protoc', BUILD + host_prefix + 'plugin'],
                               'outputs': [BUILD + prefix + 'gen/config.h'], 'deps': [protoc, plugin]}
            targets[library] = {'type': 'static_library', 'toolchain': '//build/toolchain/linux:' + chain,
                                'sources': ['//third_party/perfetto/runtime.cc', BUILD + prefix + 'gen/config.h'],
                                'deps': [action, zlib], 'libs': [builtins_archive(cpu)],
                                'defines': ['V8_TARGET_ARCH_ARM64'] if role == 'snapshot' and architecture == 'arm64' else []}
        return {'target_arch': architecture, 'targets': targets, 'pool': []}, (chromium, perfetto, jsoncpp), label

    def test_runtime_and_snapshot_keep_host_tools_and_output_roots(self):
        for architecture in ('x64', 'arm64'):
            with self.subTest(architecture=architecture), tempfile.TemporaryDirectory() as temporary:
                graph, roots, label = self.fixture(Path(temporary), architecture)
                for role in ('target', 'execution', 'snapshot'):
                    profile = capture(graph, *roots, target_arch=architecture, role=role)
                    runtime = profile['libraries'][label(ROOT, role)]
                    self.assertEqual(runtime['architecture'], architecture if role == 'target' else 'x64')
                    action = profile['actions'][label('//third_party/perfetto:generate', role)]
                    self.assertEqual(set(action['tools'].values()), {label('//third_party/protobuf:protoc', 'execution'), label('//third_party/perfetto:plugin', 'execution')})
                    prefix = '' if role == 'target' or architecture == 'x64' else ('clang_x64/' if role == 'execution' else 'clang_x64_v8_arm64/')
                    self.assertEqual(action['generated_include_roots'], [prefix + 'gen'])
                    self.assertEqual(profile['libraries'][label('//third_party/perfetto:plugin', 'execution')]['architecture'], 'x64')
                    if architecture == 'arm64':
                        self.assertTrue(all(owner is None for owner in profile['external'].values()))
                        if role == 'snapshot':
                            self.assertEqual(runtime['defines'], ['V8_TARGET_ARCH_ARM64'])
                    elif role == 'target':
                        self.assertEqual(profile['external'][label('//third_party/zlib:zlib', role)], '@electron_v8_support_sources//:zlib')

    def test_wrong_runtime_and_generator_builtins_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            graph, roots, label = self.fixture(Path(temporary), 'arm64')
            for original, wrong in [(ROOT, 'x64'), ('//third_party/perfetto:plugin', 'arm64')]:
                invalid = copy.deepcopy(graph)
                identity = label(original, 'target' if original == ROOT else 'execution')
                invalid['targets'][identity]['libs'] = [builtins_archive(wrong)]
                with self.assertRaisesRegex(ValueError, 'Untranslated Perfetto link library'):
                    capture(invalid, *roots, target_arch='arm64')
            with self.assertRaises(ValueError):
                capture(graph, *roots, target_arch='x64')
            (roots[1] / 'runtime.cc').unlink()
            with self.assertRaisesRegex(ValueError, 'Missing original Perfetto input'):
                capture(graph, *roots, target_arch='arm64')


if __name__ == '__main__':
    unittest.main()

"""Select CPU-specific zlib sources without changing snapshot compiler CPU."""

import copy
from pathlib import Path
import tempfile
import unittest

from capture_target import builtins_archive
from capture_v8_support import ROOTS, REVISIONS, TARGETS, capture


class V8SupportCaptureTest(unittest.TestCase):
    def fixture(self, temporary):
        root = Path(temporary)
        roots = {'chromium': root / 'chromium'}
        roots.update({name: root / name for name in ROOTS})
        for directory in roots.values():
            directory.mkdir()
        deps = "'highway_revision': '" + REVISIONS['highway'] + "'\n"
        for name, revision in REVISIONS.items():
            deps += "'src/" + ROOTS[name] + "':\n  " + ("Var('highway_revision')" if name == 'highway' else "'" + revision + "'") + '\n'
        (roots['chromium'] / 'DEPS').write_text(deps)
        for path in ('LICENSE', 'build/build_config.h', 'build/buildflag.h'):
            source = roots['chromium'] / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text('original header')
        for directory in list(roots.values())[1:]:
            (directory / 'public.h').write_text('original header')
            (directory / 'unit.c').write_text('original source')
        targets = {}
        for role, chain, cpu in [('target', 'clang_arm64', 'arm64'), ('execution', 'clang_x64', 'x64'), ('snapshot', 'clang_x64_v8_arm64', 'x64')]:
            suffix = '' if role == 'target' else '(//build/toolchain/linux:' + chain + ')'
            labels = [label for label in TARGETS if (label.endswith(':zlib_arm_crc32') if cpu == 'arm64' else label.endswith(':zlib_crc32_simd')) or not label.startswith('//third_party/zlib:') or label.endswith((':zlib', ':zlib_common_headers'))]
            for bare in labels:
                family = bare.split('/')[3].split(':')[0]
                target = {'type': 'static_library', 'toolchain': '//build/toolchain/linux:' + chain,
                          'sources': ['//'+ROOTS[family]+'/unit.c'], 'deps': [],
                          'cflags': ['-O2'], 'libs': [builtins_archive(cpu)],
                          'include_dirs': ['//out/bazel-import/' + ('' if role == 'target' else chain + '/') + 'gen/']}
                if bare == '//third_party/zlib:zlib':
                    target['deps'] = ['//third_party/zlib:' + name + suffix for name in ('zlib_common_headers', 'zlib_arm_crc32' if cpu == 'arm64' else 'zlib_crc32_simd')]
                targets[bare + suffix] = target
        return {'target_arch': 'arm64', 'targets': targets, 'pool': []}, roots

    def test_arm_runtime_and_x64_tools_keep_different_simd_closures(self):
        with tempfile.TemporaryDirectory() as temporary:
            graph, roots = self.fixture(temporary)
            for role in ('target', 'execution', 'snapshot'):
                result = capture(graph, roots, 'arm64', role)
                libraries = result['libraries']
                crc = 'zlib_arm_crc32' if role == 'target' else 'zlib_crc32_simd'
                other = 'zlib_crc32_simd' if role == 'target' else 'zlib_arm_crc32'
                self.assertIn(crc, libraries['zlib']['deps'])
                self.assertNotIn(other, libraries)
                self.assertEqual(libraries['zlib']['architecture'], 'arm64' if role == 'target' else 'x64')
                self.assertEqual(libraries['zlib']['srcs'], ['third_party/zlib/unit.c'])
                self.assertEqual(libraries['zlib']['copts'], ['-O2'])
                if role == 'execution':
                    self.assertTrue(all(record['family'] == 'zlib' for record in libraries.values()))
                else:
                    self.assertIn('dragonbox', libraries)
                    self.assertIn('compression_utils_portable', libraries)

    def test_cross_role_dependency_and_builtins_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            graph, roots = self.fixture(temporary)
            for field, value in [('deps', ['//third_party/zlib:zlib_crc32_simd(//build/toolchain/linux:clang_x64)']),
                                 ('libs', [builtins_archive('x64')]),
                                 ('include_dirs', ['//out/bazel-import/clang_x64/gen/'])]:
                invalid = copy.deepcopy(graph)
                invalid['targets']['//third_party/zlib:zlib'][field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    capture(invalid, roots, 'arm64')
            (roots['zlib'] / 'unit.c').unlink()
            with self.assertRaisesRegex(ValueError, 'Missing pinned V8 support input'):
                capture(graph, roots, 'arm64')


if __name__ == '__main__':
    unittest.main()

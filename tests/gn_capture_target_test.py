"""Capture original IPCz inputs for one explicit target without profile mixing."""

import copy
from pathlib import Path
import tempfile
import unittest

from capture_ipcz import ROOT, DRIVER_SOURCES, capture
from capture_base import ROOT as BASE_ROOT, BUILD, CXX, NATIVE_CPP, capture as capture_base
from capture_target import validate_graph_target, LinuxGraph
from native_graph import capture_library


class GnCaptureTargetTest(unittest.TestCase):
    def test_role_resolution_keeps_target_and_three_execution_toolchains_distinct(self):
        for architecture in ('x64', 'arm64'):
            with self.subTest(architecture=architecture):
                chains = {'target': '//build/toolchain/linux:clang_' + architecture,
                          'execution': '//build/toolchain/linux:clang_x64',
                          'snapshot': '//build/toolchain/linux:clang_x64_v8_arm64' if architecture == 'arm64' else '//build/toolchain/linux:clang_x64',
                          'rust_execution': '//build/toolchain/linux:clang_x64_for_rust_host_build_tools'}
                labels = {role: '//base:base' + ('' if chain == chains['target'] else '(' + chain + ')')
                          for role, chain in chains.items()}
                targets = {labels[role]: {'toolchain': chain} for role, chain in chains.items()}
                graph = {'target_arch': architecture, 'targets': targets}
                scope = LinuxGraph(graph, architecture)
                for role, label in labels.items():
                    self.assertEqual(scope.resolve('//base:base', role), label)
                    self.assertEqual(scope.resolve(label, role), label)
                    self.assertEqual(scope.architecture(label), architecture if role == 'target' else 'x64')
                if architecture == 'arm64':
                    with self.assertRaises(ValueError):
                        scope.resolve(labels['snapshot'], 'target')
                for label, role in [('//missing:missing', 'target'), ('//base:base', 'unknown')]:
                    with self.assertRaises(ValueError):
                        scope.resolve(label, role)
                ambiguous = copy.deepcopy(graph)
                ambiguous['targets']['//base:base(' + chains['target'] + ')'] = {'toolchain': chains['target']}
                with self.assertRaises(ValueError):
                    LinuxGraph(ambiguous, architecture).resolve('//base:base')
                inconsistent = copy.deepcopy(graph)
                inconsistent['targets'][labels['rust_execution']]['toolchain'] = chains['target']
                with self.assertRaises(ValueError):
                    LinuxGraph(inconsistent, architecture)
                with self.assertRaises(ValueError):
                    LinuxGraph(graph, 'x64' if architecture == 'arm64' else 'arm64')
                if architecture == 'arm64':
                    unmarked = {key: value for key, value in graph.items() if key != 'target_arch'}
                    with self.assertRaises(ValueError):
                        LinuxGraph(unmarked, 'x64')

    def test_native_libraries_use_each_records_cpu_including_execution_libraries(self):
        toolchains = [('clang_x64', 'x86_64-unknown-linux-gnu'),
                      ('clang_arm64', 'aarch64-unknown-linux-gnu'),
                      ('clang_x64_for_rust_host_build_tools', 'x86_64-unknown-linux-gnu'),
                      ('clang_x64_v8_arm64', 'x86_64-unknown-linux-gnu')]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = ['//lib/input' + extension for extension in ('.cc', '.c', '.S', '.h', '.m', '.mm', '.rc', '.grd')]
            for source in sources:
                path = root / source[2:]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('original source')
            for toolchain, triple in toolchains:
                with self.subTest(toolchain=toolchain):
                    builtins = '$LLVM_ROOT/lib/clang/23/lib/' + triple + '/libclang_rt.builtins.a'
                    target = {'sources': sources, 'toolchain': '//build/toolchain/linux:' + toolchain,
                              'cflags': ['--target=' + triple, '-O2'], 'libs': [builtins]}
                    if toolchain == 'clang_x64_v8_arm64':
                        target['defines'] = ['V8_TARGET_ARCH_ARM64']
                    inputs = []

                    def original_file(path):
                        self.assertTrue((root / path[2:]).is_file())
                        inputs.append(path)

                    result = capture_library({'pool': []}, target, {}, original_file, '//lib:input')
                    self.assertEqual(set(inputs), set(sources))
                    self.assertEqual(result['srcs'], ['//lib/input.cc'])
                    self.assertEqual(result['c_srcs'], ['//lib/input.c'])
                    self.assertEqual(result['asm_srcs'], ['//lib/input.S'])
                    self.assertEqual(result['gn_uncompiled_sources'], ['//lib/input.m', '//lib/input.mm'])
                    self.assertEqual(result['resource_sources'], ['//lib/input.rc', '//lib/input.grd'])
                    self.assertEqual(result['copts'], ['-O2'])
                    self.assertEqual(result['libs'], [builtins])
                    self.assertEqual(result['defines'], target.get('defines', []))
                    other = 'x86_64-unknown-linux-gnu' if triple.startswith('aarch64') else 'aarch64-unknown-linux-gnu'
                    wrong = {**target, 'libs': ['$LLVM_ROOT/lib/clang/23/lib/' + other + '/libclang_rt.builtins.a']}
                    with self.assertRaisesRegex(ValueError, 'Untranslated native library'):
                        capture_library({'pool': []}, wrong, {}, original_file, '//lib:input')

    def test_base_preserves_target_flags_and_execution_generator_identity(self):
        for architecture, triple in [('x64', 'x86_64-unknown-linux-gnu'), ('arm64', 'aarch64-unknown-linux-gnu')]:
            with self.subTest(architecture=architecture), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                chromium, boringssl, icu = [root / name for name in ('chromium', 'boringssl', 'icu')]
                files = {
                    chromium: ['base/api.cc', 'base/api.c', 'base/api.S', 'base/api.h',
                               'third_party/rust/cxx/chromium_integration/run_cxxbridge.py'],
                    boringssl: ['include/openssl/base.h'],
                    icu: ['source/common/unicode/locid.h'],
                }
                for directory, paths in files.items():
                    for path in paths:
                        destination = directory / path
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text('original source')
                toolchain = '//build/toolchain/linux:clang_' + architecture
                targets = {label: {'type': 'group', 'toolchain': toolchain, 'deps': []} for label in NATIVE_CPP}
                generator = '//base:captured_bridge'
                generated = BUILD + 'gen/base/api.h'
                host_tool = BUILD + 'clang_x64_for_rust_host_build_tools/cxxbridge'
                targets[generator] = {'type': 'action', 'toolchain': toolchain,
                                      'script': '//third_party/rust/cxx/chromium_integration/run_cxxbridge.py',
                                      'inputs': [host_tool], 'outputs': [generated], 'deps': []}
                builtins = '$LLVM_ROOT/lib/clang/23/lib/' + triple + '/libclang_rt.builtins.a'
                targets[BASE_ROOT] = {'type': 'source_set', 'toolchain': toolchain, 'deps': [generator],
                                      'sources': ['//base/api.cc', '//base/api.c', '//base/api.S', generated],
                                      'cflags': ['--target=' + triple, '-O2'],
                                      'cflags_cc': ['-std=c++20'], 'cflags_c': ['-std=c11'], 'asmflags': ['-g0'],
                                      'defines': ['CAPTURED_BASE_TARGET'], 'libs': [builtins]}
                graph = {'targets': targets, 'pool': []}
                perfetto = {'target_arch': architecture, 'names': {}}
                rust = {'target_arch': architecture, 'rust': {}}
                result = capture_base(graph, chromium, boringssl, icu, perfetto, rust, target_arch=architecture)
                library = result['libraries'][BASE_ROOT]
                self.assertEqual(result['target_arch'], architecture)
                self.assertEqual(library['copts'], ['-O2', '-std=c++20'])
                self.assertEqual(library['c_copts'], ['-O2', '-std=c11'])
                self.assertEqual(library['asm_copts'], ['-O2', '-g0'])
                self.assertEqual(library['srcs'], ['//base/api.cc'])
                self.assertEqual(library['c_srcs'], ['//base/api.c'])
                self.assertEqual(library['asm_srcs'], ['//base/api.S'])
                self.assertEqual(library['libs'], [builtins])
                self.assertEqual(result['actions'][generator]['tools'], {host_tool[2:]: CXX})
                self.assertIn('clang_x64_for_rust_host_build_tools', CXX)
                self.assertEqual(result['producers'], {generated: generator})
                self.assertIn('base/api.h', result['headers'])
                if architecture == 'x64':
                    self.assertEqual(capture_base(graph, chromium, boringssl, icu,
                                                  {'names': {}}, {'rust': {}}), result)
                other = 'arm64' if architecture == 'x64' else 'x64'
                wrong_graph = copy.deepcopy(graph)
                wrong_graph['targets'][generator]['toolchain'] = '//build/toolchain/linux:clang_' + other
                with self.assertRaisesRegex(ValueError, 'selected Linux architecture'):
                    capture_base(wrong_graph, chromium, boringssl, icu, perfetto, rust, target_arch=architecture)
                with self.assertRaisesRegex(ValueError, 'share target architecture'):
                    capture_base(graph, chromium, boringssl, icu, {**perfetto, 'target_arch': other}, rust,
                                 target_arch=architecture)

    def test_graph_root_cannot_be_relabelled_as_another_cpu(self):
        graph = {'targets': {'//electron:electron': {'toolchain': '//build/toolchain/linux:clang_x64'}}}
        with self.assertRaisesRegex(ValueError, 'root does not match'):
            validate_graph_target(graph, '//electron:electron', 'arm64')
        with self.assertRaisesRegex(ValueError, 'Unsupported captured Linux'):
            validate_graph_target(graph, '//electron:electron', 'host')

    def test_original_sources_flags_and_dependencies_for_both_targets(self):
        for architecture, triple in [('x64', 'x86_64-unknown-linux-gnu'), ('arm64', 'aarch64-unknown-linux-gnu')]:
            with self.subTest(architecture=architecture), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                files = DRIVER_SOURCES + ['third_party/ipcz/LICENSE', 'third_party/ipcz/src/api.h', 'third_party/ipcz/src/api.cc']
                for name in files:
                    destination = root / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text('original source')
                builtins = '$LLVM_ROOT/lib/clang/23/lib/' + triple + '/libclang_rt.builtins.a'
                target = {'type': 'source_set', 'toolchain': '//build/toolchain/linux:clang_' + architecture,
                          'sources': ['//third_party/ipcz/src/api.cc'], 'deps': ['//base:base'],
                          'cflags': ['--target=' + triple, '-O2'], 'defines': ['IPCZ_CAPTURED_TARGET'],
                          'include_dirs': ['//third_party/ipcz/src'], 'libs': ['dl', builtins]}
                graph = {'targets': {ROOT: target}, 'pool': []}
                base = {'target_arch': architecture, 'names': {'//base:base': 'base'}}
                result = capture(graph, root, base, target_arch=architecture)
                library = result['libraries'][ROOT]
                self.assertEqual(result['target_arch'], architecture)
                self.assertEqual(library['srcs'], ['//third_party/ipcz/src/api.cc'])
                self.assertEqual(library['copts'], ['-O2'])
                self.assertEqual(library['omitted_toolchain_and_diagnostic_flags'], ['--target=' + triple])
                self.assertEqual(library['libs'], ['dl', builtins])
                self.assertEqual(library['defines'], ['IPCZ_CAPTURED_TARGET'])
                self.assertEqual(result['files'], sorted(files))
                self.assertEqual(result['external'], {'//base:base': '@electron_base_sources//:base'})
                if architecture == 'x64':
                    legacy = {'names': {'//base:base': 'base'}}
                    self.assertEqual(capture(graph, root, legacy), result)
                wrong_graph = copy.deepcopy(graph)
                wrong_graph['targets'][ROOT]['toolchain'] = '//build/toolchain/linux:clang_' + ('arm64' if architecture == 'x64' else 'x64')
                with self.assertRaisesRegex(ValueError, 'selected Linux target'):
                    capture(wrong_graph, root, base, target_arch=architecture)
                wrong_base = {**base, 'target_arch': 'arm64' if architecture == 'x64' else 'x64'}
                with self.assertRaisesRegex(ValueError, 'share target architecture'):
                    capture(graph, root, wrong_base, target_arch=architecture)
                wrong_graph = copy.deepcopy(graph)
                other = 'aarch64-unknown-linux-gnu' if architecture == 'x64' else 'x86_64-unknown-linux-gnu'
                wrong_graph['targets'][ROOT]['libs'] = ['$LLVM_ROOT/lib/clang/23/lib/' + other + '/libclang_rt.builtins.a']
                with self.assertRaisesRegex(ValueError, 'Untranslated IPCz link library'):
                    capture(wrong_graph, root, base, target_arch=architecture)


if __name__ == '__main__':
    unittest.main()

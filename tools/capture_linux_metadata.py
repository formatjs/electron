"""Capture Linux GN metadata on BB from pinned repositories and SDKs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

from prepare_source import prepare

_EXTRA_ROOTS = {
    'third_party/icu': 'electron_icu_sources',
    'third_party/skia': 'electron_skia_upstream',
    'third_party/harfbuzz-ng/src': 'electron_harfbuzz_upstream',
    'third_party/freetype/src': 'electron_freetype_upstream',
    'third_party/fontconfig/src': 'electron_fontconfig_upstream',
    'third_party/libjpeg_turbo': 'electron_jpeg_upstream',
    'third_party/libwebp/src': 'electron_webp_upstream',
    'third_party/wuffs/src': 'electron_wuffs_upstream',
    'third_party/nasm': 'electron_nasm_upstream',
    'third_party/jsoncpp/source': 'electron_jsoncpp_upstream',
    'third_party/protobuf-javascript/src': 'electron_protobuf_javascript_upstream',
    'third_party/crabbyavif/src': 'electron_crabbyavif_upstream',
    'third_party/lss': 'electron_lss_upstream',
    'net/third_party/quiche/src': 'electron_quiche_upstream',
    'third_party/re2/src': 'electron_re2_upstream',
    'third_party/snappy/src': 'electron_snappy_upstream',
    'third_party/libdrm/src': 'electron_libdrm_upstream',
    'third_party/libsync/src': 'electron_libsync_upstream',
    'third_party/ced/src': 'electron_ced_upstream',
    'third_party/zstd/src': 'electron_zstd_upstream',
    'third_party/fp16/src': 'electron_fp16_upstream',
    'third_party/dragonbox/src': 'electron_dragonbox_upstream',
    'third_party/fast_float/src': 'electron_fast_float_upstream',
    'third_party/highway/src': 'electron_highway_upstream',
    'third_party/node/linux': 'electron_chromium_node_tool',
}


class MissingRepository(ValueError):
    def __init__(self, name):
        super().__init__('Expected one pinned source repository')
        self.repository = name


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def resolve_output(execution_root, path):
    output = (execution_root / Path(path)).resolve(strict=True)
    if not output.is_file():
        raise ValueError('Expected one Bazel output file')
    return output


def repository(root, name):
    matches = [path for path in root.iterdir() if path.name == name + '+' or path.name.endswith('+' + name)]
    if len(matches) != 1 or not matches[0].is_dir():
        raise MissingRepository(name)
    return matches[0].resolve()


def rust_sysroot(inputs, destination):
    for component in ('rustc', 'rust_std_x64', 'rust_std_arm64'):
        root = (inputs / component).resolve()
        for directory in ('bin', 'lib') if component == 'rustc' else ('lib',):
            source = root / directory
            if not source.is_dir():
                raise ValueError('Missing pinned Rust component')
            for path in sorted(source.rglob('*')):
                target = destination / path.relative_to(root)
                if path.is_symlink() and (not path.resolve().is_relative_to(root) or not path.is_file()):
                    raise ValueError('Rust component link escapes declared files')
                if path.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif path.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        if digest(target) != digest(path):
                            raise ValueError('Rust components disagree on shared file')
                    else:
                        if directory == 'bin':
                            shutil.copy2(path, target)
                        else:
                            target.symlink_to(path.resolve())
                else:
                    raise ValueError('Unexpected Rust component entry')
    return destination


def capture(args):
    print('GN_METADATA_PHASE inputs', flush=True)
    inputs, overlay, output = args.capture_inputs, args.overlay_root, args.output
    if not (inputs / 'capture_inputs.json').is_file():
        raise ValueError('Missing capture input manifest')
    pins = json.loads((inputs / 'capture_inputs.json').read_text())
    gn = inputs / 'gn/gn'
    if not gn.is_file():
        raise ValueError('Missing declared GN executable')
    if digest(gn) != pins['gn_binary_sha256']:
        raise ValueError('Pinned GN executable changed')
    if not (args.llvm_root / 'lib/clang/23/include/stddef.h').is_file():
        raise ValueError('Missing declared LLVM resource headers')
    if not args.pkg_config.is_file():
        raise ValueError('Missing declared package tool')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='electron-gn-capture-') as temporary:
        temporary = Path(temporary)
        source = temporary / 'src'
        print('GN_METADATA_PHASE repositories', flush=True)
        packages = json.loads((overlay / 'bcr/overlay/source/upstream_pins.json').read_text())
        dependencies = {}
        for package in packages:
            if package['group'] not in {'chromium', 'node', 'v8'}:
                name = 'electron_' + package['group'].lower().replace('.', '_').replace('-', '_') + '_sources'
                dependencies[package['repo'].removeprefix('src/')] = repository(args.repositories, name)
        profile = json.loads((overlay / 'bcr/overlay/source/native/platform_inputs.json').read_text())
        for prefix, pin in profile['source_revisions'].items():
            if prefix in dependencies:
                continue
            suffix = prefix.removeprefix('third_party/').replace('-', '_').replace('/', '_').lower()
            dependencies[prefix] = repository(args.repositories, 'electron_platform_' + suffix)
        for prefix, name in _EXTRA_ROOTS.items():
            dependencies[prefix] = repository(args.repositories, name)
        dependencies['third_party/node/node_modules'] = repository(args.repositories, 'electron_chromium_webui_upstream') / 'node_modules'
        for path, name in [('third_party/cast_core/public/src', 'electron_cast_core_sources'),
                           ('third_party/glslang/src', 'electron_glslang_sources')]:
            dependencies[path] = repository(args.repositories, name)
        for architecture, suffix in [('amd64', 'x64'), ('arm64', 'arm64')]:
            dependencies['build/linux/debian_bullseye_' + architecture + '-sysroot'] = inputs / ('sysroot_' + suffix)
        fingerprints = overlay / 'bcr/overlay/source/patch_fingerprints.json'
        print('GN_METADATA_PHASE prepare', flush=True)
        prepare(repository(args.repositories, 'electron_chromium_sources'), repository(args.repositories, 'electron'),
                repository(args.repositories, 'electron_node_sources'), repository(args.repositories, 'electron_v8_sources'),
                None, source, dependencies=sorted(dependencies.items(), key=lambda item: (len(Path(item[0]).parts), item[0])),
                fingerprints=json.loads(fingerprints.read_text()))
        print('GN_METADATA_PHASE rust-sysroot', flush=True)
        rust = rust_sysroot(inputs, temporary / 'rust')
        tools = temporary / 'bin'
        tools.mkdir()
        for name, path in [('python3', Path(sys.executable)), ('python', Path(sys.executable)), ('pkg-config', args.pkg_config)]:
            (tools / name).symlink_to(path)
        empty = temporary / 'empty-pkgconfig'
        empty.mkdir()
        environment = {'PATH': str(tools), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC',
                       'PYTHONNOUSERSITE': '1', 'PKG_CONFIG_LIBDIR': str(empty), 'PKG_CONFIG_PATH': ''}

        def run(command, phase):
            result = subprocess.run([str(value) for value in command], cwd=source, env=environment,
                                    capture_output=True, text=True, timeout=600)
            if result.returncode:
                report = {'phase': phase, 'exit_code': result.returncode}
                match = re.search(r'(?m)^ERROR at //([A-Za-z0-9_./+-]+):(\d+):(\d+):', result.stdout + result.stderr)
                if match and '..' not in Path(match[1]).parts and (source / match[1]).is_file():
                    report.update(file=match[1], line=int(match[2]), column=int(match[3]))
                print('GN_METADATA_COMMAND_FAILED ' + json.dumps(report, sort_keys=True))
                raise ValueError('Metadata command failed')
            return result.stdout

        print('GN_METADATA_PHASE rust-version', flush=True)
        if run([rust / 'bin/rustc', '-V'], 'rust-version').strip() != pins['rustc_version']:
            raise ValueError('Pinned Rust compiler version changed')
        build = source / 'out/bazel-import'
        build.mkdir(parents=True)
        configuration = '\n'.join([
            'import("//electron/build/args/all.gn")', 'is_debug = false', 'is_component_build = false',
            'is_official_build = false', 'symbol_level = 0', 'chrome_pgo_phase = 0', 'target_os = "linux"',
            'target_cpu = ' + json.dumps(args.target_arch), 'override_electron_version = "39.0.0"',
            'clang_base_path = ' + json.dumps(str(args.llvm_root)), 'clang_version = "23"',
            'clang_use_chrome_plugins = false', 'rust_sysroot_absolute = ' + json.dumps(str(rust)),
            'rustc_version = ' + json.dumps(pins['rustc_version']), 'angle_build_tests = false',
            'pkg_config = ' + json.dumps(str(args.pkg_config)), 'host_pkg_config = ' + json.dumps(str(args.pkg_config)),
        ]) + '\n'
        (build / 'args.gn').write_text(configuration)
        options = ['--root=' + str(source), '--root-target=//electron:electron', '--script-executable=' + sys.executable]
        print('GN_METADATA_PHASE gn-gen', flush=True)
        run([gn, 'gen', build, *options, '--ide=json', '--json-file-name=project.json'], 'gn-gen')
        print('GN_METADATA_PHASE gn-desc', flush=True)
        raw = run([gn, 'desc', build, '//electron:electron_app', 'runtime_deps', '--format=json', *options], 'gn-desc')
        runtime = temporary / 'runtime.json'
        runtime_data = json.loads(raw[raw.index('{'):])
        runtime.write_text(json.dumps(runtime_data))
        graph = output / ('linux-' + args.target_arch + '-graph.json.gz')
        print('GN_METADATA_PHASE serialize', flush=True)
        run([sys.executable, Path(__file__).with_name('capture_source.py'), '--chromium-tools', inputs / 'chromium_tools/tools',
             '--source-root', source, '--llvm-root', args.llvm_root, '--rust-root', rust, '--gn', gn,
             '--runtime-deps', runtime, '--patch-fingerprints', fingerprints, '--output', graph,
             '--target-arch', args.target_arch, '--pkg-config', args.pkg_config], 'serialize')
        report = {'pins': pins, 'llvm_clang_sha256': digest(args.llvm_root / 'bin/clang'),
                  'pkgconf_sha256': digest(args.pkg_config), 'python_version': platform.python_version(),
                  'capture_script_sha256': digest(Path(__file__))}
        (output / 'capture-inputs.json').write_text(json.dumps(report, indent=2) + '\n')
        summary = json.loads(graph.with_suffix('.summary.json').read_text())
        print('GN_METADATA_CAPTURED ' + json.dumps({'target_arch': args.target_arch, 'targets': summary['target_count'],
                                                   'graph_sha256': summary['graph_sha256']}, sort_keys=True))


def main():
    if not os.environ.get('BUILDBUDDY_ARTIFACTS_DIRECTORY') or sys.platform != 'linux' or platform.machine() not in ('x86_64', 'AMD64'):
        print('GN_METADATA_REQUIRES_BB_LINUX_X64', file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('capture-inputs', 'overlay-root', 'repositories', 'pkg-config', 'llvm-root', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--target-arch', choices=('x64', 'arm64'), default='arm64')
    try:
        capture(parser.parse_args())
    except MissingRepository as error:
        report = {'reason': 'SOURCE_REPOSITORY'}
        if re.fullmatch(r'electron(?:_[a-z0-9_]+)?', error.repository):
            report['repository'] = error.repository
        print('GN_METADATA_CAPTURE_FAILED ' + json.dumps(report, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as error:
        reasons = {
            'Missing capture input manifest': 'INPUT_MANIFEST',
            'Missing declared GN executable': 'GN_EXECUTABLE',
            'Pinned GN executable changed': 'GN_DIGEST',
            'Missing declared LLVM resource headers': 'LLVM_HEADERS',
            'Missing declared package tool': 'PACKAGE_TOOL',
            'Missing pinned Rust component': 'RUST_COMPONENT',
            'Rust component link escapes declared files': 'RUST_LINK',
            'Rust components disagree on shared file': 'RUST_COLLISION',
            'Pinned Rust compiler version changed': 'RUST_VERSION',
            'Metadata command failed': 'COMMAND',
        }
        reason = reasons.get(str(error), {'FileNotFoundError': 'FILE_MISSING', 'TimeoutExpired': 'TIMEOUT',
                                          'JSONDecodeError': 'INVALID_JSON'}.get(type(error).__name__, 'INTERNAL'))
        print('GN_METADATA_CAPTURE_FAILED ' + json.dumps({'reason': reason}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Project captured support inputs for native compiler validation on BB."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

from capture_linux_metadata import repository, source_roots
from capture_v8_support import ROOTS as SUPPORT_ROOTS
from capture_protobuf import ROOTS as PROTOBUF_ROOTS
from capture_perfetto import ROOTS as PERFETTO_ROOTS
from capture_target import toolchain_architecture


def stage(profile_path, graph_path, roots, build_file, destination, kind="v8-support"):
    prefixes = {"v8-support": SUPPORT_ROOTS, "protobuf": PROTOBUF_ROOTS, "perfetto": PERFETTO_ROOTS}[kind]
    with profile_path.open("rb") as stream:
        content = stream.read(16 * 1024**2 + 1)
    if len(content) > 16 * 1024**2:
        raise ValueError('Support profile exceeds limit')
    profile = json.loads(content)
    with graph_path.open('rb') as stream:
        graph_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    role = profile.get('role')
    if (profile.get('target_arch') != 'arm64' or role not in ('target', 'execution', 'snapshot')
            or profile.get('graph_sha256') != graph_sha256 or profile.get('roots') != prefixes
            or not profile.get('libraries')):
        raise ValueError('Invalid support profile identity')
    if kind == 'perfetto':
        selected = '//build/toolchain/linux:' + ('clang_arm64' if role == 'target' else 'clang_x64' if role == 'execution' else 'clang_x64_v8_arm64')
        records = list(profile['libraries'].values()) + list(profile['actions'].values())
        if any(record.get('toolchain') not in (selected, '//build/toolchain/linux:clang_x64')
               or record.get('architecture') != toolchain_architecture(record.get('toolchain')) for record in records):
            raise ValueError('Perfetto compiler role changed')
    elif any(record.get('architecture') != ('arm64' if role == 'target' else 'x64')
           for record in profile['libraries'].values()):
        raise ValueError('Support compiler architecture changed')
    files = {}
    for logical in profile['files']:
        path = PurePosixPath(logical)
        if (not isinstance(logical, str) or logical != path.as_posix() or path.is_absolute()
                or '\\' in logical or '..' in path.parts or logical in files):
            raise ValueError('Invalid support source path')
        owner = next((name for name, prefix in prefixes.items() if logical.startswith(prefix + '/')), None)
        if owner:
            physical = roots[owner] / logical.removeprefix(prefixes[owner] + '/')
        elif logical in ('LICENSE', 'build/build_config.h', 'build/buildflag.h') or kind == 'perfetto' and logical == 'tools/protoc_wrapper/protoc_wrapper.py':
            physical = roots['chromium'] / logical
        else:
            raise ValueError('Unowned support source path')
        if not physical.is_file():
            raise ValueError('Missing declared support input')
        files[logical] = physical.resolve()
    build = build_file.read_text()
    if kind == 'protobuf':
        dependencies = profile.get('abseil_gn_deps')
        prefix = '//third_party/abseil-cpp/'
        chain = 'clang_arm64' if role == 'target' else 'clang_x64' if role == 'execution' else 'clang_x64_v8_arm64'
        suffix = '' if role == 'target' else '(//build/toolchain/linux:' + chain + ')'
        if not dependencies or len(dependencies) != len(set(dependencies)):
            raise ValueError('Missing or duplicate Abseil identities')
        owners = []
        for dependency in dependencies:
            bare = dependency.split('(')[0]
            if not bare.startswith(prefix + 'absl/') or dependency != bare + suffix:
                raise ValueError('Abseil owner crosses compiler role')
            owners.append('@electron_abseil_sources//' + bare.removeprefix(prefix))
        if build.count('electron_protobuf()') != 1:
            raise ValueError('Unexpected Protobuf build template')
        build = build.replace('electron_protobuf()', 'electron_protobuf(abseil_deps = ' + repr(owners) + ')')
    if kind == 'perfetto':
        suffix = '' if role == 'target' else '(//build/toolchain/linux:' + ('clang_x64' if role == 'execution' else 'clang_x64_v8_arm64') + ')'
        execution = '(//build/toolchain/linux:clang_x64)'
        owners = {'//third_party/protobuf:protoc' + execution: '@electron_protobuf_sources//:protoc',
                  '//third_party/protobuf:protoc_lib' + execution: '@electron_protobuf_sources//:protoc_lib',
                  '//third_party/zlib:zlib' + suffix: '@electron_v8_support_sources//:zlib'}
        if set(profile['external']) != set(owners) or build.count('electron_perfetto()') != 1:
            raise ValueError('Unexpected Perfetto external identities or template')
        build = build.replace('electron_perfetto()', 'electron_perfetto(external = ' + repr(owners) + ')')
    destination.mkdir(parents=True, exist_ok=False)
    for logical, physical in files.items():
        target = destination / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(physical)
    (destination / 'profile.bzl').write_text('PROFILE = json.decode(' + json.dumps(content.decode()) + ')\n')
    (destination / 'BUILD.bazel').write_text(build)
    (destination / 'MODULE.bazel').write_text('module(name = "electron_support_profile")\n')
    return role, len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('profile', 'graph', 'repositories', 'overlay-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument("--kind", choices=("v8-support", "protobuf", "perfetto"), default="v8-support")
    args = parser.parse_args()
    prefixes = {"v8-support": SUPPORT_ROOTS, "protobuf": PROTOBUF_ROOTS, "perfetto": PERFETTO_ROOTS}[args.kind]
    try:
        dependencies = source_roots(args.overlay_root)
        roots = {'chromium': repository(args.repositories, 'electron_chromium_sources')}
        for name, prefix in prefixes.items():
            if prefix in dependencies:
                repo, _, subdirectory = dependencies[prefix]
                roots[name] = repository(args.repositories, repo) / subdirectory
            else:
                roots[name] = roots['chromium'] / prefix
        role, count = stage(args.profile, args.graph, roots, args.overlay_root / ('bcr/overlay/source/' + args.kind.replace('-', '_') + '.BUILD.bazel'), args.output, args.kind)
    except Exception:
        print('SUPPORT_PROFILE_STAGE_FAILED', file=sys.stderr)
        return 1
    print('SUPPORT_PROFILE_STAGED module=' + args.kind + ' role=' + role + ' files=' + str(count))
    return 0


if __name__ == '__main__':
    sys.exit(main())

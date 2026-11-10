"""Project captured support inputs for native compiler validation on BB."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

from capture_linux_metadata import repository, source_roots
from capture_v8_support import ROOTS


def stage(profile_path, graph_path, roots, build_file, destination):
    with profile_path.open("rb") as stream:
        content = stream.read(16 * 1024**2 + 1)
    if len(content) > 16 * 1024**2:
        raise ValueError('Support profile exceeds limit')
    profile = json.loads(content)
    with graph_path.open('rb') as stream:
        graph_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    role = profile.get('role')
    if (profile.get('target_arch') != 'arm64' or role not in ('target', 'execution', 'snapshot')
            or profile.get('graph_sha256') != graph_sha256 or profile.get('roots') != ROOTS
            or not profile.get('libraries')):
        raise ValueError('Invalid support profile identity')
    if any(record.get('architecture') != ('arm64' if role == 'target' else 'x64')
           for record in profile['libraries'].values()):
        raise ValueError('Support compiler architecture changed')
    files = {}
    for logical in profile['files']:
        path = PurePosixPath(logical)
        if (not isinstance(logical, str) or logical != path.as_posix() or path.is_absolute()
                or '\\' in logical or '..' in path.parts or logical in files):
            raise ValueError('Invalid support source path')
        owner = next((name for name, prefix in ROOTS.items() if logical.startswith(prefix + '/')), None)
        if owner:
            physical = roots[owner] / logical.removeprefix(ROOTS[owner] + '/')
        elif logical in ('LICENSE', 'build/build_config.h', 'build/buildflag.h'):
            physical = roots['chromium'] / logical
        else:
            raise ValueError('Unowned support source path')
        if not physical.is_file():
            raise ValueError('Missing declared support input')
        files[logical] = physical.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for logical, physical in files.items():
        target = destination / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(physical)
    (destination / 'profile.bzl').write_text('PROFILE = json.decode(' + json.dumps(content.decode()) + ')\n')
    (destination / 'BUILD.bazel').write_bytes(build_file.read_bytes())
    (destination / 'MODULE.bazel').write_text('module(name = "electron_support_profile")\n')
    return role, len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('profile', 'graph', 'repositories', 'overlay-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        dependencies = source_roots(args.overlay_root)
        roots = {'chromium': repository(args.repositories, 'electron_chromium_sources')}
        for name, prefix in ROOTS.items():
            if prefix in dependencies:
                repo, _, subdirectory = dependencies[prefix]
                roots[name] = repository(args.repositories, repo) / subdirectory
            else:
                roots[name] = roots['chromium'] / prefix
        role, count = stage(args.profile, args.graph, roots, args.overlay_root / 'bcr/overlay/source/v8_support.BUILD.bazel', args.output)
    except Exception:
        print('SUPPORT_PROFILE_STAGE_FAILED', file=sys.stderr)
        return 1
    print('SUPPORT_PROFILE_STAGED role=' + role + ' files=' + str(count))
    return 0


if __name__ == '__main__':
    sys.exit(main())

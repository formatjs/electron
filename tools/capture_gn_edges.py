#!/usr/bin/env python3
"""Capture GN dependency kinds without executing build actions."""

import argparse
from contextlib import contextmanager
import hashlib
import gzip
import json
from pathlib import Path
import re
import subprocess
import tempfile


_METADATA = '''
      _bazel_existing_metadata = {}
      if (defined(metadata)) {
        _bazel_existing_metadata = metadata
      }
      metadata = {}
      metadata = {
        forward_variables_from(_bazel_existing_metadata, "*")
        bazel_private_deps = []
        bazel_public_deps = []
        bazel_data_deps = []
        if (defined(deps)) {
          foreach(_bazel_dep, deps) {
            bazel_private_deps += [ get_label_info(_bazel_dep, "label_with_toolchain") ]
          }
        }
        if (defined(public_deps)) {
          foreach(_bazel_dep, public_deps) {
            bazel_public_deps += [ get_label_info(_bazel_dep, "label_with_toolchain") ]
          }
        }
        if (defined(data_deps)) {
          foreach(_bazel_dep, data_deps) {
            bazel_data_deps += [ get_label_info(_bazel_dep, "label_with_toolchain") ]
          }
        }
      }
'''


def instrument(source):
    # Mask comments/strings while preserving offsets for balanced target scopes.
    masked = re.sub(r'"(?:\\.|[^"\\])*"|#[^\n]*', lambda m: ' ' * len(m[0]), source)
    edits = []
    for opening in ('target(_target_type, target_name) {', 'target(_target_type, _target_name) {'):
        if source.count(opening) != 1:
            raise ValueError('Unexpected Chromium target wrapper: ' + opening)
        start = source.index(opening) + len(opening)
        depth = 1
        for index in range(start, len(source)):
            depth += (masked[index] == '{') - (masked[index] == '}')
            if not depth:
                edits.append(index)
                break
        else:
            raise ValueError('Unclosed GN target wrapper')
    for index in sorted(edits, reverse=True):
        source = source[:index] + _METADATA + source[index:]
    source += '''
foreach(_bazel_type, [ "group", "action", "action_foreach", "copy", "generated_file", "rust_library", "rust_proc_macro", "bundle_data", "create_bundle" ]) {
  template(_bazel_type) {
    _bazel_target_name = target_name
    target(_bazel_type, _bazel_target_name) {
      forward_variables_from(invoker, "*", TESTONLY_AND_VISIBILITY + [ "deps", "public_deps", "data_deps" ])
      forward_variables_from(invoker, TESTONLY_AND_VISIBILITY + [ "deps", "public_deps", "data_deps" ])
''' + _METADATA + '''
    }
  }
}
'''
    return source


def dependency_kinds(graph):
    result = {}
    targets = graph['targets']
    for label, target in targets.items():
        metadata = target.get('metadata', {})
        row = {}
        for name in ('private', 'public', 'data'):
            key = 'bazel_' + name + '_deps'
            if key not in metadata:
                raise ValueError('Missing typed dependency capture: ' + label)
            values = []
            for dependency in metadata[key]:
                without_toolchain = dependency.split('(', 1)[0]
                values.append(without_toolchain if without_toolchain in targets and targets[without_toolchain]['toolchain'] == dependency.split('(', 1)[1][:-1] else dependency)
            row[name] = values
        if set(target.get('deps', [])) != set(row['private'] + row['public'] + row['data']):
            raise ValueError('Dependency capture differs from GN graph: ' + label)
        result[label] = row
    return result


def write_capture(baseline, captured, output, config_digest):
    if baseline.keys() != captured.keys() or baseline['targets'].keys() != captured['targets'].keys():
        raise ValueError('Instrumentation changed graph structure')
    if any(baseline[key] != captured[key] for key in baseline if key != "targets"):
        raise ValueError("Instrumentation changed build settings or toolchains")
    for label, original in baseline['targets'].items():
        instrumented = captured['targets'][label]
        if {k: v for k, v in original.items() if k != 'metadata'} != {k: v for k, v in instrumented.items() if k != 'metadata'}:
            raise ValueError('Instrumentation changed target: ' + label)
        if any(instrumented.get('metadata', {}).get(k) != v for k, v in original.get('metadata', {}).items()):
            raise ValueError('Instrumentation changed original metadata: ' + label)
    result = dict(buildconfig_sha256=config_digest, targets=dependency_kinds(captured))
    output.write_bytes(gzip.compress(json.dumps(result, sort_keys=True, separators=(',', ':')).encode(), mtime=0))
    print('Verified typed edges for ' + str(len(result['targets'])) + ' unchanged targets')


def split_dependencies(label, dependencies, capture):
    row = capture['targets'].get(label)
    if row is None or set(dependencies) != set(row['private'] + row['public'] + row['data']):
        raise ValueError('Typed dependencies do not match source graph: ' + label)
    links = set(row['private'] + row['public'])
    return dict(gn_link_deps=[dep for dep in dependencies if dep in links],
                gn_data_deps=[dep for dep in dependencies if dep not in links])


@contextmanager
def private_config(config):
    original = config.read_bytes()
    with tempfile.TemporaryDirectory(prefix='.gn-edges-', dir=config.parent) as temporary:
        backup = Path(temporary) / config.name
        config.rename(backup)
        try:
            config.write_bytes(original)
            yield original
        finally:
            config.unlink(missing_ok=True)
            backup.rename(config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gn', type=Path, required=True)
    parser.add_argument('--chromium-root', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = args.chromium_root / 'build/config/BUILDCONFIG.gn'
    original = config.read_bytes()
    subprocess.run([str(args.gn), 'gen', str(args.out_dir), '--ide=json', '--json-file-name=baseline-typed-project.json'], cwd=args.chromium_root, check=True)
    with private_config(config):
        config.write_text(instrument(original.decode()))
        subprocess.run([str(args.gn), 'gen', str(args.out_dir), '--ide=json', '--json-file-name=typed-project.json'], cwd=args.chromium_root, check=True)
    digest = hashlib.sha256(original).hexdigest()
    print('Original BUILDCONFIG.gn restored; SHA256 ' + digest)
    write_capture(json.loads((args.out_dir / 'baseline-typed-project.json').read_text()), json.loads((args.out_dir / 'typed-project.json').read_text()), args.output, digest)


if __name__ == '__main__':
    main()

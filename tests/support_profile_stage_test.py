"""Profile projection checks identity before exposing declared source files."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from capture_v8_support import ROOTS
from capture_protobuf import ROOTS as PROTOBUF_ROOTS
from stage_support_profile import stage


class SupportProfileStageTest(unittest.TestCase):
    def test_exact_projection_and_rejection_before_destination_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            (source / 'public.h').write_text('pinned source')
            graph, build, profile = [root / name for name in ('graph.gz', 'BUILD.bazel', 'profile.json')]
            graph.write_bytes(b'captured graph')
            build.write_text('native build definition')
            record = {'target_arch': 'arm64', 'role': 'target', 'roots': ROOTS,
                      'graph_sha256': hashlib.sha256(graph.read_bytes()).hexdigest(),
                      'files': ['third_party/zlib/public.h'], 'libraries': {'zlib': {'architecture': 'arm64'}}}
            roots = {'zlib': source}
            profile.write_text(json.dumps(record))
            destination = root / 'projection'
            self.assertEqual(stage(profile, graph, roots, build, destination), ('target', 1))
            self.assertEqual((destination / 'third_party/zlib/public.h').resolve(), source / 'public.h')
            self.assertEqual((destination / 'BUILD.bazel').read_bytes(), build.read_bytes())
            self.assertEqual((source / 'public.h').read_text(), 'pinned source')
            with self.assertRaises(FileExistsError):
                stage(profile, graph, roots, build, destination)
            for field, value in [('target_arch', 'x64'), ('role', 'unknown'), ('graph_sha256', '0' * 64),
                                 ('libraries', {'zlib': {'architecture': 'x64'}}),
                                 ('files', ['third_party/zlib/../private.h']), ('files', ['unowned.h']),
                                 ('files', ['third_party/zlib/missing.h']),
                                 ('files', ['third_party/zlib/public.h'] * 2)]:
                invalid = dict(record, **{field: value})
                profile.write_text(json.dumps(invalid))
                rejected = root / 'rejected'
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    stage(profile, graph, roots, build, rejected)
                self.assertFalse(rejected.exists())

    def test_protobuf_binds_exact_role_abseil_owners(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            (source / 'public.h').write_text('pinned protobuf header')
            graph, build, profile = [root / name for name in ('graph.gz', 'BUILD.bazel', 'profile.json')]
            graph.write_bytes(b'captured graph')
            build.write_text('electron_protobuf()\n')
            for role, suffix in [('target', ''), ('execution', '(//build/toolchain/linux:clang_x64)'),
                                 ('snapshot', '(//build/toolchain/linux:clang_x64_v8_arm64)')]:
                record = {'target_arch': 'arm64', 'role': role, 'roots': PROTOBUF_ROOTS,
                          'graph_sha256': hashlib.sha256(graph.read_bytes()).hexdigest(),
                          'files': ['third_party/protobuf/public.h'],
                          'libraries': {'protobuf_lite': {'architecture': 'arm64' if role == 'target' else 'x64'}},
                          'abseil_gn_deps': ['//third_party/abseil-cpp/absl/base:base' + suffix]}
                profile.write_text(json.dumps(record))
                output = root / role
                self.assertEqual(stage(profile, graph, {'protobuf': source}, build, output, 'protobuf'), (role, 1))
                self.assertEqual((output / 'BUILD.bazel').read_text(), "electron_protobuf(abseil_deps = ['@electron_abseil_sources//absl/base:base'])\n")
                self.assertIn(record['abseil_gn_deps'][0], (output / 'profile.bzl').read_text())
                record['abseil_gn_deps'] = ['//third_party/abseil-cpp/absl/base:base' + ('' if suffix else '(//build/toolchain/linux:clang_x64)')]
                profile.write_text(json.dumps(record))
                rejected = root / ('rejected-' + role)
                with self.assertRaisesRegex(ValueError, 'Abseil owner crosses compiler role'):
                    stage(profile, graph, {'protobuf': source}, build, rejected, 'protobuf')
                self.assertFalse(rejected.exists())


if __name__ == '__main__':
    unittest.main()

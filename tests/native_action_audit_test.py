"""The action gate fails closed on wrappers, empty graphs and malformed output."""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import redirect_stdout
import io

from tools.audit_native_actions import FORBIDDEN, action_count, audit_summaries, main


COMPILERS = "17 total actions.\n\nMnemonics:\n  CppCompile: 17\n\nConfigurations:\n  k8-opt: 17\n"
EMPTY = "No actions matched.\n"


class NativeActionAuditTest(unittest.TestCase):
    def test_real_native_graph_without_wrappers_passes(self):
        self.assertEqual(audit_summaries(COMPILERS, EMPTY), 17)

    def test_wrappers_and_missing_compilers_fail(self):
        wrapper = "1 total action.\n\nMnemonics:\n  ForeignCc: 1\n"
        for compilers, wrappers in ((COMPILERS, wrapper), (EMPTY, EMPTY),
                                    (COMPILERS.replace("CppCompile", "Symlink"), EMPTY)):
            with self.subTest(compilers=compilers, wrappers=wrappers), self.assertRaises(ValueError):
                audit_summaries(compilers, wrappers)

    def test_unknown_truncated_or_inconsistent_summaries_fail(self):
        for text in ("", "No actions matched.\nunknown", "17 total actions.\n",
                     COMPILERS.replace("CppCompile: 17", "CppCompile: 16"),
                     COMPILERS.replace("CppCompile: 17", "CppCompile: invalid")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                action_count(text)

    def test_support_audit_uses_same_repository_and_platform_for_both_queries(self):
        for target in ("@electron_v8_support_sources//:libraries", "@electron_protobuf_sources//:libraries", "@electron_perfetto_native_sources//:libraries"):
            for platform in ('linux_arm64', 'linux_amd64'):
                arguments = ['audit', '--registry=file:///registry', '--downloader-config=/downloader',
                             '--distdir=/distdir', '--target=' + target,
                             '--support-override=electron+sources=/declared/profile',
                             '--support-override=electron+compiler=/declared/compiler', '--support-platform=' + platform]
                with patch('sys.argv', arguments), patch('subprocess.run', side_effect=[SimpleNamespace(stdout=COMPILERS), SimpleNamespace(stdout=EMPTY)]) as run, redirect_stdout(io.StringIO()):
                    self.assertEqual(main(), 0)
                    self.assertEqual(run.call_count, 2)
                    for call in run.call_args_list:
                        command = call.args[0]
                        self.assertIn('--override_repository=electron+sources=/declared/profile', command)
                        self.assertIn('--override_repository=electron+compiler=/declared/compiler', command)
                        self.assertIn('--platforms=@electron//source/platforms:' + platform, command)
                        self.assertIn('deps(' + target + ')', command[-1])
                        self.assertNotIn('source_tests', command[-1])
                        self.assertEqual(call.kwargs, {'check': True, 'capture_output': True, 'text': True})

    def test_wrapper_filter_preserves_native_generators(self):
        for mnemonic in ("ForeignCc", "ForeignCcMake", "CMake", "Cmake", "Meson", "Ninja", "Make", "GMake", "RunMake", "GN", "RunGN"):
            with self.subTest(mnemonic=mnemonic):
                self.assertIsNotNone(re.search(FORBIDDEN, mnemonic))
        for mnemonic in ("CppCompile", "CppLink", "ElectronPython", "ElectronNodeConfig", "MakeSymlinks"):
            with self.subTest(mnemonic=mnemonic):
                self.assertIsNone(re.search(FORBIDDEN, mnemonic))


if __name__ == "__main__":
    unittest.main()

"""The action gate fails closed on wrappers, empty graphs and malformed output."""

import re
import unittest

from tools.audit_native_actions import FORBIDDEN, action_count, audit_summaries


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

    def test_wrapper_filter_preserves_native_generators(self):
        for mnemonic in ("ForeignCc", "ForeignCcMake", "CMake", "Cmake", "Meson", "Ninja", "Make"):
            with self.subTest(mnemonic=mnemonic):
                self.assertIsNotNone(re.search(FORBIDDEN, mnemonic))
        for mnemonic in ("CppCompile", "CppLink", "ElectronPython", "ElectronNodeConfig", "MakeSymlinks"):
            with self.subTest(mnemonic=mnemonic):
                self.assertIsNone(re.search(FORBIDDEN, mnemonic))


if __name__ == "__main__":
    unittest.main()

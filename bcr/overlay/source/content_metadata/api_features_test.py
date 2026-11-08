# SPDX-License-Identifier: MIT
"""Check original feature tables retain declared API names and source year."""

import json
from pathlib import Path
import re
import runpy
import sys
import unittest

COMMENT_EATER = runpy.run_path(sys.argv[1])["Nom"]
CASES = [json.loads(value) for value in sys.argv[2:]]
del sys.argv[1:]


class APIFeatures(unittest.TestCase):
    def test_generated_feature_tables_preserve_all_source_keys_and_declared_year(self):
        self.assertEqual(len(CASES), 13)
        for case in CASES:
            with self.subTest(method=case["method"]):
                names = set()
                for source in case["sources"]:
                    names.update(json.loads(COMMENT_EATER(Path(source).read_text())))
                implementation = Path(case["implementation"]).read_text()
                header = Path(case["header"]).read_text()
                registered = re.findall(r'provider->AddFeature\("([^"\n]+)", feature\);', implementation)
                self.assertEqual(len(registered), len(set(registered)))
                self.assertEqual(set(registered), names)
                self.assertIn("void " + case["method"] + "(FeatureProvider* provider);", header)
                for output in (implementation, header):
                    self.assertIn("// Copyright 2025 The Chromium Authors", output)


if __name__ == "__main__":
    unittest.main()

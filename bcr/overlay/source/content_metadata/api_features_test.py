# SPDX-License-Identifier: MIT
"""Check original feature tables retain merged compilable API names and source year."""

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
    def test_generated_feature_tables_match_merged_compilable_sources_and_declared_year(self):
        self.assertEqual(len(CASES), 13)
        for case in CASES:
            with self.subTest(method=case["method"]):
                overrides = {str(Path(path).with_name(Path(path).name.replace(".override.", ".", 1))): Path(path) for path in case["overrides"]}
                self.assertLessEqual(set(overrides), set(case["sources"]))
                definitions = {}
                for source in case["sources"]:
                    feature = json.loads(COMMENT_EATER(Path(source).read_text()))
                    if source in overrides:
                        feature.update(json.loads(COMMENT_EATER(overrides[source].read_text())))
                    definitions.update(feature)
                names = set()
                for name, feature in definitions.items():
                    if isinstance(feature, dict) and "nocompile" in feature:
                        self.assertTrue(feature["nocompile"])
                    else:
                        names.add(name)
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

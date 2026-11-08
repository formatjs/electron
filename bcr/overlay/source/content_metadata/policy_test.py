# SPDX-License-Identifier: MIT
"""Check source policy IDs and Linux schema survive template generation."""

import json
from pathlib import Path
import sys
import unittest

YAML_INIT, POLICY_IDS, HOMEPAGE, TEMPLATES, DEPFILE = [Path(value) for value in sys.argv[1:]]
sys.argv[1:] = []
sys.path.insert(0, str(YAML_INIT.resolve().parent.parent))
import pyyaml


class Policy(unittest.TestCase):
    def test_pinned_yaml_runtime_and_policy_ids_match_sources(self):
        self.assertTrue(Path(pyyaml.__file__).samefile(YAML_INIT))
        source = pyyaml.safe_load(POLICY_IDS.read_text())["policies"]
        generated = json.loads(TEMPLATES.read_text())
        policies = {item["name"]: item for item in generated["policy_definitions"] if "id" in item}
        self.assertEqual({name: item["id"] for name, item in policies.items()},
                         {name: identifier for identifier, name in source.items() if name})
        self.assertEqual(set(generated["deleted_policy_ids"]),
                         {identifier for identifier, name in source.items() if not name})
        original = pyyaml.safe_load(HOMEPAGE.read_text())
        for field in ("schema", "type", "features", "supported_on"):
            with self.subTest(field=field):
                self.assertEqual(policies["HomepageLocation"][field], original[field])

    def test_depfile_uses_declared_relative_policy_paths(self):
        target, sources = DEPFILE.read_text().split(": ", 1)
        self.assertEqual(target, "gen/chrome/app/policy/policy_templates.json")
        paths = sources.split()
        self.assertGreater(len(paths), 0)
        self.assertTrue(all(path.startswith("../../components/policy/resources/templates/")
                            and path.endswith(".yaml") for path in paths))
        self.assertIn("../../components/policy/resources/templates/policies.yaml", paths)


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: MIT
"""Check original Chromium generators against their declared source metadata."""

import json
from pathlib import Path
import re
import sys
import unittest


VERSION_HEADER, REVISION_HEADER, VERSION, BRANDING, LASTCHANGE = sys.argv[1:]
del sys.argv[1:]


def fields(path):
    return dict(line.split("=", 1) for line in Path(path).read_text().splitlines() if "=" in line)


def macros(path):
    return dict(re.findall(r"^#define ([A-Z_]+) (.+)$", Path(path).read_text(), re.MULTILINE))


class MetadataTest(unittest.TestCase):
    def test_version_header_matches_source_metadata(self):
        version = fields(VERSION)
        branding = fields(BRANDING)
        revision = fields(LASTCHANGE)
        self.assertEqual(macros(VERSION_HEADER), {
            "PRODUCT_NAME": json.dumps(branding["PRODUCT_FULLNAME"]),
            "PRODUCT_VERSION": json.dumps(".".join(version[key] for key in ("MAJOR", "MINOR", "BUILD", "PATCH"))),
            "LAST_CHANGE": json.dumps(revision["LASTCHANGE"]),
            "IS_OFFICIAL_BUILD": "0",
        })

    def test_git_revision_uses_original_gn_truncation(self):
        revision = fields(LASTCHANGE)["LASTCHANGE"].split("-", 1)[0]
        self.assertEqual(macros(REVISION_HEADER), {"CHROMIUM_GIT_REVISION": json.dumps("@" + revision)})


if __name__ == "__main__":
    unittest.main()

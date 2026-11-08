# SPDX-License-Identifier: MIT
"""Check the original standalone tracing viewer's packaged resource contract."""

from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
import unittest

NODE, HTML, JAVASCRIPT = map(Path, sys.argv[1:])
del sys.argv[1:]


class References(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.scripts = []
        self.imports = []
        self.feed(document)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "script" and "src" in attributes:
            self.scripts.append(attributes["src"])
        if tag == "link" and attributes.get("rel") == "import":
            self.imports.append(attributes.get("href"))


class CatapultTest(unittest.TestCase):
    def test_standalone_html_uses_chromium_tracing_route(self):
        references = References(HTML.read_text())
        self.assertEqual(references.scripts, ["tracing.js"])
        self.assertEqual(references.imports, [])

    def test_minified_viewer_contains_entrypoint_and_parses(self):
        contents = JAVASCRIPT.read_text()
        self.assertIn("tr.ui.e.about_tracing", contents)
        self.assertIn("profilingView", contents)
        subprocess.run([str(NODE.resolve()), "--check", str(JAVASCRIPT.resolve())],
                       check=True, env={"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "NODE_PATH": "", "NODE_OPTIONS": ""})


if __name__ == "__main__":
    unittest.main()

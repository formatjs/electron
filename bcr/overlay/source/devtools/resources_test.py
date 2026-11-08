"""Check original DevTools locale collection and HTML entrypoint generation."""

from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import unittest


LOCALE, HTML = sys.argv[1:]
del sys.argv[1:]


class Scripts(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.modules = []
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type") == "module":
            self.modules.append(attrs.get("src"))


class ResourcesTest(unittest.TestCase):
    def test_locale_collects_strings_from_multiple_frontend_directories(self):
        locale = json.loads(Path(LOCALE).read_text(encoding="utf-8"))
        for identifier, message in {
            "panels/elements/ElementsPanel.ts | styles": "Styles",
            "panels/network/NetworkLogView.ts | clearBrowserCache": "Clear browser cache",
        }.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(locale[identifier]["message"], message)

    def test_html_boots_actual_devtools_entrypoint(self):
        document = Path(HTML).read_text(encoding="utf-8")
        self.assertEqual(Scripts(document).modules, ["./entrypoints/devtools_app/devtools_app.js"])
        self.assertNotIn("%ENTRYPOINT_NAME%", document)


if __name__ == "__main__":
    unittest.main()

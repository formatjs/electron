# SPDX-License-Identifier: MIT
"""Check original Chromium/Electron payloads and final resource routing."""

import gzip
from pathlib import Path
import re
import struct
import subprocess
import sys
import unittest

(HEADER, PACK, HTML, JAVASCRIPT, NODE, COMPONENT_HEADER, COMPONENT_PACK,
 DISTILLER, READABILITY, READERABLE, FINAL_PACK, ELECTRON_HEADER,
 DISCOVERY_HTML) = [Path(value) for value in sys.argv[1:]]
sys.argv[1:] = []


def resources(path):
    contents = path.read_bytes()
    version, encoding, count, aliases = struct.unpack_from("<IB3xHH", contents)
    if version != 5 or encoding not in (0, 1, 2):
        raise ValueError("Expected Chromium DataPack v5")
    entries = [struct.unpack_from("<HI", contents, 12 + index * 6)
               for index in range(count + 1)]
    start = 12 + (count + 1) * 6 + aliases * 4
    offsets = [offset for _, offset in entries]
    if offsets != sorted(offsets) or offsets[0] < start or offsets[-1] != len(contents):
        raise ValueError("Invalid Chromium resource offsets")
    result = {identifier: contents[offset:entries[index + 1][1]]
              for index, (identifier, offset) in enumerate(entries[:-1])}
    for index in range(aliases):
        identifier, target = struct.unpack_from("<HH", contents, 12 + (count + 1) * 6 + index * 4)
        result[identifier] = result[entries[target][0]]
    return result


class ContentWebUI(unittest.TestCase):
    def test_tracing_pack_preserves_original_html_and_javascript(self):
        identifiers = dict((name, int(value)) for name, value in re.findall(
            r"^#define (IDR_TRACING_\w+) (\d+)$", HEADER.read_text(), re.MULTILINE))
        payloads = resources(PACK)
        for name, original in [("IDR_TRACING_ABOUT_TRACING_HTML", HTML),
                               ("IDR_TRACING_ABOUT_TRACING_JS", JAVASCRIPT)]:
            with self.subTest(resource=name):
                payload = payloads[identifiers[name]]
                if payload.startswith(b"\x1f\x8b"):
                    payload = gzip.decompress(payload)
                self.assertEqual(payload, original.read_bytes())

    def test_distiller_pack_inlines_pinned_javascript_and_preserves_valid_syntax(self):
        identifiers = dict((name, int(value)) for name, value in re.findall(
            r"^#define (IDR_\w+) (\d+)$", COMPONENT_HEADER.read_text(), re.MULTILINE))
        payloads = resources(COMPONENT_PACK)
        for name, original in [
            ("IDR_DISTILLER_JS", DISTILLER),
            ("IDR_READABILITY_DISTILLER_JS", READABILITY),
            ("IDR_READABILITY_TRIGGERING_JS", READERABLE),
        ]:
            with self.subTest(resource=name):
                payload = payloads[identifiers[name]]
                if payload.startswith(b"\x1f\x8b"):
                    payload = gzip.decompress(payload)
                text = payload.decode("utf-8")
                self.assertIn(original.read_text().strip(), text)
                self.assertNotRegex(text, r'<include\b[^>]*\bsrc=')
                subprocess.run([str(NODE.resolve()), "--check"], input=payload, check=True,
                               env={"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"})

    def test_electron_repack_preserves_discovery_page_and_component_payloads(self):
        electron_ids = dict((name, int(value)) for name, value in re.findall(
            r"^#define (IDR_\w+) (\d+)$", ELECTRON_HEADER.read_text(), re.MULTILINE))
        component_ids = dict((name, int(value)) for name, value in re.findall(
            r"^#define (IDR_\w+) (\d+)$", COMPONENT_HEADER.read_text(), re.MULTILINE))
        final = resources(FINAL_PACK)
        components = resources(COMPONENT_PACK)
        self.assertEqual(final[electron_ids["IDR_CONTENT_SHELL_DEVTOOLS_DISCOVERY_PAGE"]], DISCOVERY_HTML.read_bytes())
        for name in ("IDR_DISTILLER_JS", "IDR_READABILITY_DISTILLER_JS", "IDR_READABILITY_TRIGGERING_JS"):
            with self.subTest(resource=name):
                identifier = component_ids[name]
                self.assertEqual(final[identifier], components[identifier])


if __name__ == "__main__":
    unittest.main()

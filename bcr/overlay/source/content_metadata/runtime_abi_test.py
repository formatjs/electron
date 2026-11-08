# SPDX-License-Identifier: MIT
"""Check pinned SDK interfaces match executable printing/fence libraries."""

from pathlib import Path
import struct
import sys
import unittest

CUPS_SDK, CUPS_RUNTIME, FENCE_SDK, FENCE_RUNTIME, PIXBUF_SDK, PIXBUF_RUNTIME = map(Path, sys.argv[1:])
sys.argv[1:] = []


def sections(path):
    contents = path.read_bytes()
    if contents[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected declared little endian ELF64")
    offset = struct.unpack_from("<Q", contents, 40)[0]
    size, count, names = struct.unpack_from("<HHH", contents, 58)
    headers = [struct.unpack_from("<IIQQQQIIQQ", contents, offset + index * size)
               for index in range(count)]
    header = headers[names]
    strings = contents[header[4]:header[4] + header[5]]
    return {strings[header[0]:].split(b"\0", 1)[0].decode():
            contents[header[4]:header[4] + header[5]] for header in headers}


class RuntimeABI(unittest.TestCase):
    def test_sdk_interfaces_match_pinned_runtime_symbols_and_build_ids(self):
        for name, sdk_path, runtime_path in [("cups", CUPS_SDK, CUPS_RUNTIME),
                                              ("xshmfence", FENCE_SDK, FENCE_RUNTIME),
                                              ("gdk-pixbuf", PIXBUF_SDK, PIXBUF_RUNTIME)]:
            with self.subTest(library=name):
                sdk, runtime = sections(sdk_path), sections(runtime_path)
                self.assertNotIn(".text", sdk)
                self.assertTrue(runtime[".text"])
                for section in [".dynsym", ".dynstr", ".note.gnu.build-id"]:
                    self.assertIn(section, sdk)
                    self.assertEqual(sdk[section], runtime.get(section))
                for section in [".gnu.version", ".gnu.version_d"]:
                    self.assertEqual(sdk.get(section), runtime.get(section))


if __name__ == "__main__":
    unittest.main()

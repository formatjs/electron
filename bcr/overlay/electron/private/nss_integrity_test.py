# SPDX-License-Identifier: MIT
"""Published RFC 6979 DSA-2048/SHA-256 conformance vectors."""

import hashlib
import unittest

from nss_integrity import nonce


class NonceTest(unittest.TestCase):
    def test_rfc6979_appendix_a_2_2(self):
        # https://www.rfc-editor.org/rfc/rfc6979#appendix-A.2.2
        q = int("F2C3119374CE76C9356990B465374A17F23F9ED35089BD969F61C6DDE9998C1F", 16)
        private = int("69C7548C21D0DFEA6B9A51C9EAD4E27C33D3B3F180316E5BCAB92C933F0E4DBC", 16)
        for message, expected in [
            (b"sample", "8926A27C40484216F052F4427CFD5647338B7B3939BC6573AF4333569D597C52"),
            (b"test", "1D6CE6DDA1C5D37307839CD03AB0A5CBB18E60D800937D67DFB4479AAC8DEAD7"),
        ]:
            with self.subTest(message=message):
                self.assertEqual(nonce(q, private, hashlib.sha256(message).digest()).hex().upper(), expected)


if __name__ == "__main__":
    unittest.main()

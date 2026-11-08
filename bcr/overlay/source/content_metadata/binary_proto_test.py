# SPDX-License-Identifier: MIT
"""Check real binary policies through their generated protobuf bindings."""

import os
from pathlib import Path
import sys
import unittest

(RUNTIME_INIT, DOWNLOAD_MODULE, SSL_MODULE, DOWNLOAD_PAYLOAD, SSL_PAYLOAD,
 DOWNLOAD_SOURCE, SSL_SOURCE) = map(Path, sys.argv[1:])
del sys.argv[1:]
os.environ["PROTOBUF_PYTHON_IMPLEMENTATION"] = "python"
sys.path[:0] = [str(RUNTIME_INIT.parents[2]), str(DOWNLOAD_MODULE.parent), str(SSL_MODULE.parent)]

import google.protobuf
from google.protobuf import text_format
from google.protobuf.internal import api_implementation
import download_file_types_pb2
import ssl_error_assistant_pb2


class BinaryProtoTest(unittest.TestCase):
    def test_pure_python_runtime_comes_from_declared_files(self):
        self.assertTrue(Path(google.protobuf.__file__).samefile(RUNTIME_INIT))
        self.assertEqual(api_implementation.Type(), "python")

    def test_linux_file_types_select_settings_and_preserve_policy_identity(self):
        actual = download_file_types_pb2.DownloadFileTypeConfig.FromString(DOWNLOAD_PAYLOAD.read_bytes())
        source = text_format.Parse(DOWNLOAD_SOURCE.read_text(), download_file_types_pb2.DownloadFileTypeConfig())
        self.assertEqual(actual.version_id, source.version_id)
        self.assertEqual(actual.sampled_ping_probability, source.sampled_ping_probability)
        self.assertEqual([(t.extension, t.uma_value) for t in actual.file_types],
                         [(t.extension, t.uma_value) for t in source.file_types])
        for file_type in [actual.default_file_type, *actual.file_types]:
            with self.subTest(extension=file_type.extension):
                self.assertEqual(len(file_type.platform_settings), 1)
                self.assertFalse(file_type.platform_settings[0].HasField("platform"))
        policy = download_file_types_pb2.DownloadFileType
        expected = {
            "pl": (policy.ALLOW_ON_USER_GESTURE, policy.DISALLOW_AUTO_OPEN),
            "crx": (policy.ALLOW_ON_USER_GESTURE, policy.ALLOW_AUTO_OPEN),
            "exe": (policy.NOT_DANGEROUS, policy.ALLOW_AUTO_OPEN),
        }
        types = {t.extension: t for t in actual.file_types}
        for extension, settings in expected.items():
            with self.subTest(extension=extension):
                setting = types[extension].platform_settings[0]
                self.assertEqual((setting.danger_level, setting.auto_open_hint), settings)

    def test_ssl_payload_matches_declared_policy(self):
        actual = ssl_error_assistant_pb2.SSLErrorAssistantConfig.FromString(SSL_PAYLOAD.read_bytes())
        source = text_format.Parse(SSL_SOURCE.read_text(), ssl_error_assistant_pb2.SSLErrorAssistantConfig())
        self.assertEqual(actual, source)


if __name__ == "__main__":
    unittest.main()

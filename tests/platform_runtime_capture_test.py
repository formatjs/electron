"""Capture exact SDK package bytes without mixing target architectures."""

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from tools.pin_platform_runtime import main


def debian_archive(control, path, binary):
    result = bytearray(b'!<arch>\n')
    for name, files in [('control.tar.gz', {'control': control.encode()}), ('data.tar.gz', {path: binary})]:
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w:gz') as archive:
            for filename, contents in files.items():
                entry = tarfile.TarInfo(filename)
                entry.size = len(contents)
                archive.addfile(entry, io.BytesIO(contents))
        contents = data.getvalue()
        header = f'{name + "/":<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(contents):<10}`\n'
        result.extend(header.encode() + contents + (b'\n' if len(contents) % 2 else b''))
    return bytes(result)


class PlatformRuntimeCaptureTest(unittest.TestCase):
    def test_sdk_layout_identity_and_original_archive_digest_for_both_targets(self):
        for architecture, triple, explicit in [('amd64', 'x86_64-linux-gnu', False), ('arm64', 'aarch64-linux-gnu', True)]:
            with self.subTest(architecture=architecture), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                sdk, cache = root / 'sdk', root / 'cache'
                cache.mkdir()
                relative = 'usr/lib/' + triple + '/libfixture.so.1.2'
                interface = sdk / relative
                interface.parent.mkdir(parents=True)
                interface.write_bytes(b'SDK interface')
                interface.with_name('libfixture.so.1').symlink_to(interface.name)
                metadata = sdk / 'debian/libfixture1/DEBIAN'
                metadata.mkdir(parents=True)
                control = 'Package: libfixture1\nVersion: 1.2-3\nArchitecture: ' + architecture + '\nSource: fixture\n'
                (metadata / 'control').write_text(control)
                binary = b'original package runtime bytes'
                digest = hashlib.md5(binary).hexdigest()
                (metadata / 'md5sums').write_text(digest + '  ' + relative + '\n')
                archive = debian_archive(control, relative, binary)
                (cache / ('libfixture1_1.2-3_' + architecture + '.deb')).write_bytes(archive)
                manifest = root / 'manifest.json'
                value = {'libraries': {}, 'system_libraries': ['libc.so.6'], 'packages': [], 'root_libraries': []}
                if explicit:
                    value['architecture'] = architecture
                manifest.write_text(json.dumps(value))
                output = root / 'output.json'
                argv = ['capture', '--sdk', str(sdk), '--cache', str(cache), '--manifest', str(manifest),
                        '--output', str(output), '--root', 'libfixture.so.1']
                if explicit:
                    argv += ['--architecture', architecture]
                with patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()), patch(
                        'tools.pin_platform_runtime.subprocess.check_output', return_value='(SONAME) [libfixture.so.1]\n(NEEDED) [libc.so.6]') as readelf, patch(
                        'tools.pin_platform_runtime.urllib.request.urlopen') as network:
                    main()
                network.assert_not_called()
                readelf.assert_called_once_with(['readelf', '-d', str(cache / 'libfixture.so.1.elf')], text=True)
                result = json.loads(output.read_text())
                self.assertEqual(result['architecture'], architecture)
                self.assertEqual(result['libraries']['libfixture.so.1'], {
                    'package': 'libfixture1', 'interface': relative, 'needed': ['libc.so.6'],
                    'url': result['packages'][0]['url'], 'md5': digest,
                })
                self.assertEqual(result['packages'][0]['sha256'], hashlib.sha256(archive).hexdigest())
                self.assertTrue(result['packages'][0]['url'].endswith('_' + architecture + '.deb'))
                self.assertEqual((cache / 'libfixture.so.1.elf').read_bytes(), binary)
                self.assertEqual(json.loads(manifest.read_text()), value)
                output.unlink()
                other = 'arm64' if architecture == 'amd64' else 'amd64'
                (metadata / 'control').write_text(control.replace('Architecture: ' + architecture, 'Architecture: ' + other))
                with patch.object(sys, 'argv', argv), patch('tools.pin_platform_runtime.subprocess.check_output') as readelf, patch(
                        'tools.pin_platform_runtime.urllib.request.urlopen') as network:
                    with self.assertRaisesRegex(ValueError, 'package architecture'):
                        main()
                network.assert_not_called()
                readelf.assert_not_called()
                self.assertFalse(output.exists())

    def test_mixed_manifest_architecture_fails_before_fetch_or_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / 'manifest.json'
            manifest.write_text('{"architecture":"amd64"}')
            argv = ['capture', '--sdk', str(root / 'sdk'), '--cache', str(root / 'cache'),
                    '--manifest', str(manifest), '--output', str(root / 'output.json'),
                    '--root', 'libfixture.so.1', '--architecture', 'arm64']
            with patch.object(sys, 'argv', argv), patch('tools.pin_platform_runtime.urllib.request.urlopen') as network:
                with self.assertRaisesRegex(ValueError, 'manifest architecture'):
                    main()
            network.assert_not_called()
            self.assertFalse((root / 'cache').exists())
            self.assertFalse((root / 'output.json').exists())


if __name__ == '__main__':
    unittest.main()

# SPDX-License-Identifier: MIT
"""Launch the relocated source-built executable with no build-tree search paths."""

import json
import os
from pathlib import Path
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.sax.saxutils import escape

ARCHIVE = Path(sys.argv[1])
COUNT = int(sys.argv[2])
REQUIRED = sys.argv[3:3 + COUNT]
SMOKE_ASAR = Path(sys.argv[-2])
FONT = Path(sys.argv[-1])
del sys.argv[1:]


def run_checked(*arguments, **options):
    result = subprocess.run(*arguments, **options)
    if result.returncode:
        sys.stderr.write(result.stderr[:24000])
        result.check_returncode()
    return result


def write_alias_fixture(resources):
    module = b"module.exports = {answer: 42};\n"
    packed = b"packed fixture\n"
    files = {
        "native": {"files": {"answer.cjs": {"size": len(module), "unpacked": True}}},
        "directory": {"link": "native"},
        "alias.cjs": {"link": "directory/answer.cjs"},
        "chain.cjs": {"link": "alias.cjs"},
        "root": {"link": ""},
        "packed.bin": {"size": len(packed), "offset": "0"},
        "packed-alias.bin": {"link": "packed.bin"},
        "cycle-a": {"link": "cycle-b"},
        "cycle-b": {"link": "cycle-a"},
    }
    encoded = json.dumps({"files": files}, separators=(",", ":")).encode()
    payload = struct.pack("<I", len(encoded)) + encoded
    payload += b"\0" * (-len(payload) % 4)
    header = struct.pack("<I", len(payload)) + payload
    (resources / "links.asar").write_bytes(struct.pack("<II", 4, len(header)) + header + packed)
    sidecar = resources / "links.asar.unpacked/native"
    sidecar.mkdir(parents=True)
    (sidecar / "answer.cjs").write_bytes(module)


class RuntimeTest(unittest.TestCase):
    def test_relocated_node_browser_ipc_and_rendering(self):
        with tempfile.TemporaryDirectory(prefix="source Electron relocated 世界 ") as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(ARCHIVE) as archive:
                self.assertTrue(set(REQUIRED) <= set(archive.namelist()))
                for info in archive.infolist():
                    destination = (root / info.filename).resolve()
                    self.assertTrue(destination.is_relative_to(root))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    destination.chmod((info.external_attr >> 16) & 0o777)
            fonts = root / "fonts"
            fonts.mkdir()
            (root / "font-cache").mkdir()
            shutil.copyfile(FONT, fonts / "fixture.ttf")
            configuration = root / "fonts.conf"
            configuration.write_text('<fontconfig><dir>' + escape(str(fonts)) + '</dir><cachedir>' +
                                     escape(str(root / "font-cache")) + '</cachedir></fontconfig>')
            environment = {"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "HOME": str(root),
                           "FONTCONFIG_FILE": str(configuration), "FONTCONFIG_PATH": str(root)}
            node = run_checked([str(root / "electron"), "-e", "console.log(JSON.stringify(process.versions))"],
                                  cwd=root, env=dict(environment, ELECTRON_RUN_AS_NODE="1"),
                                  capture_output=True, text=True, timeout=60)
            versions = json.loads(node.stdout)
            self.assertEqual(versions["electron"], "39.0.0")
            self.assertEqual(versions["node"], "22.20.0")
            browser = run_checked([str(root / "electron"), "--version", "--no-sandbox"],
                                  cwd=root, env=environment, capture_output=True, text=True, timeout=60)
            self.assertEqual(browser.stdout.strip(), "v39.0.0")
            shutil.copyfile(SMOKE_ASAR, root / "resources/app.asar")
            write_alias_fixture(root / "resources")
            program = (root / "electron").rename(root / "source-runtime-smoke")
            process = subprocess.Popen([str(program), "--no-sandbox", "--ozone-platform=headless",
                                        "--disable-gpu", "--disable-dev-shm-usage", "--force-device-scale-factor=1",
                                        "--force-color-profile=srgb", "--disable-background-networking",
                                        "--disable-component-update", "--no-first-run"],
                                       cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, start_new_session=True)
            try:
                output, errors = process.communicate(timeout=90)
                self.assertEqual(process.returncode, 0, errors)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
            reports = [json.loads(line.removeprefix("SOURCE_RUNTIME_BROWSER_SMOKE:")) for line in output.splitlines()
                       if line.startswith("SOURCE_RUNTIME_BROWSER_SMOKE:")]
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0], {"answer": 42, "nodeIntegration": False, "packaged": True, "fromAsar": True,
                                          "asarAliases": True,
                                          "size": {"width": 64, "height": 64},
                                          "channels": [18, 52, 86], "alpha": 255})


if __name__ == "__main__":
    unittest.main()

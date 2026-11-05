# SPDX-License-Identifier: MIT
"""Launch a packaged example on its native OS and verify rendering."""
import argparse
import os
import platform
import stat
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path


def smoke(archive, screenshot):
    with tempfile.TemporaryDirectory(prefix="electron-smoke-") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                path = root / entry.filename
                if not path.resolve().is_relative_to(root):
                    raise ValueError(f"Unsafe archive path: {entry.filename}")
                path.parent.mkdir(parents=True, exist_ok=True)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode):
                    target = source.read(entry).decode()
                    if not (path.parent / target).resolve().is_relative_to(root):
                        raise ValueError(f"Unsafe archive link: {entry.filename}")
                    path.symlink_to(target)
                else:
                    path.write_bytes(source.read(entry))
                    path.chmod(stat.S_IMODE(mode) or 0o644)
        system = platform.system()
        executable = root / ("Hello.exe" if system == "Windows" else "Hello.app/Contents/MacOS/Hello" if system == "Darwin" else "Hello")
        if system == "Darwin":
            # Rebranding invalidates upstream signatures. Smoke artifacts use ad hoc signing.
            subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(root / "Hello.app")], check=True)
        environment = dict(os.environ, ELECTRON_SMOKE_OUTPUT=str(screenshot))
        subprocess.run([str(executable), "--no-sandbox", "--disable-gpu"], env=environment, check=True, timeout=90)
        image = screenshot.read_bytes()
        if image[:8] != b"\x89PNG\r\n\x1a\n" or len(image) < 1000:
            raise ValueError("Missing rendered PNG")
        width, height = struct.unpack(">II", image[16:24])
        if width < 600 or height < 400:
            raise ValueError(f"Unexpected screenshot size: {width}x{height}")
        print(f"Rendered packaged app: {width}x{height}, {len(image)} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    arguments = parser.parse_args()
    smoke(arguments.package.resolve(), arguments.screenshot.resolve())

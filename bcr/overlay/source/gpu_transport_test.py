# SPDX-License-Identifier: MIT
"""Run native GPU command transport with its declared shared-library closure."""

from pathlib import Path
import subprocess
import sys
import tempfile

if len(sys.argv) != 7:
    raise ValueError("Expected probe, Dawn revision, EGL, driver manifest, SDK, native GLib")
probe = Path(sys.argv[1]).absolute()
revision = sys.argv[2]
egl, icd, sdk, glib = [Path(value).absolute() for value in sys.argv[3:]]
with tempfile.TemporaryDirectory(prefix="electron-gpu-transport-") as scratch:
    environment = {
        "PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC",
        "LD_LIBRARY_PATH": str(egl.parent) + ":" + str(glib.parent) + ":" + str(sdk.parent),
        "VK_DRIVER_FILES": str(icd), "VK_ICD_FILENAMES": str(icd),
        "VK_LOADER_LAYERS_DISABLE": "~all~", "VK_LAYER_PATH": scratch,
        "XDG_DATA_DIRS": scratch, "XDG_CONFIG_DIRS": scratch,
        "XDG_CACHE_HOME": scratch, "TMPDIR": scratch,
    }
    result = subprocess.run([str(probe), revision], env=environment)
    raise SystemExit(result.returncode)

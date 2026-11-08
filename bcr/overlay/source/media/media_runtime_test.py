# SPDX-License-Identifier: MIT
"""Run native media checks with declared desktop shared libraries."""

from pathlib import Path
import subprocess
import sys
import tempfile

if len(sys.argv) < 6:
    raise ValueError("Expected probe, EGL, driver manifest, SDK and native GLib")
probe, egl, icd, sdk, glib = [Path(value).absolute() for value in sys.argv[1:6]]
with tempfile.TemporaryDirectory(prefix="electron-native-media-") as scratch:
    environment = {
        "PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC",
        "LD_LIBRARY_PATH": str(egl.parent) + ":" + str(glib.parent) + ":" + str(sdk.parent),
        "VK_DRIVER_FILES": str(icd), "VK_ICD_FILENAMES": str(icd),
        "VK_LOADER_LAYERS_DISABLE": "~all~", "VK_LAYER_PATH": scratch,
        "XDG_DATA_DIRS": scratch, "XDG_CONFIG_DIRS": scratch,
        "XDG_CACHE_HOME": scratch, "TMPDIR": scratch,
    }
    result = subprocess.run([str(probe), *sys.argv[6:]], env=environment)
    raise SystemExit(result.returncode)

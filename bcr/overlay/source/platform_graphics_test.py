# SPDX-License-Identifier: MIT
"""Run original ANGLE/SwiftShader code with declared shared libraries only."""

from pathlib import Path
import subprocess
import sys
import tempfile

if len(sys.argv) != 7:
    raise ValueError("Expected declared probe, EGL, GLES, driver manifest SDK library and native GLib")
probe, egl, gles, icd, sdk, glib = [Path(value).absolute() for value in sys.argv[1:]]
with tempfile.TemporaryDirectory(prefix="electron-native-graphics-") as scratch:
    result = subprocess.run([str(probe), str(egl), str(gles)], env={
        "PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC",
        "LD_LIBRARY_PATH": str(egl.parent) + ":" + str(glib.parent) + ":" + str(sdk.parent),
        "VK_DRIVER_FILES": str(icd), "VK_ICD_FILENAMES": str(icd),
        "VK_LOADER_LAYERS_DISABLE": "~all~", "VK_LAYER_PATH": scratch,
        "XDG_DATA_DIRS": scratch, "XDG_CONFIG_DIRS": scratch,
        "XDG_CACHE_HOME": scratch, "TMPDIR": scratch,
    })
    print(f"[DEBUG-native-graphics] exit {result.returncode}", flush=True)
    raise SystemExit(result.returncode)

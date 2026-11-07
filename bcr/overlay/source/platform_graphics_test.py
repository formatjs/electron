# SPDX-License-Identifier: MIT
"""Run original ANGLE/SwiftShader code with declared shared libraries only."""

from pathlib import Path
import hashlib
import re
import subprocess
import sys
import tempfile

if len(sys.argv) != 8:
    raise ValueError("Expected declared probe, EGL, GLES, driver manifest, SDK, native GLib and symbolizer")
probe, egl, gles, icd, sdk, glib, symbolizer = [Path(value).absolute() for value in sys.argv[1:]]
with tempfile.TemporaryDirectory(prefix="electron-native-graphics-") as scratch:
    environment = {
        "PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC",
        "LD_LIBRARY_PATH": str(egl.parent) + ":" + str(glib.parent) + ":" + str(sdk.parent),
        "VK_DRIVER_FILES": str(icd), "VK_ICD_FILENAMES": str(icd),
        "VK_LOADER_LAYERS_DISABLE": "~all~", "VK_LAYER_PATH": scratch,
        "XDG_DATA_DIRS": scratch, "XDG_CONFIG_DIRS": scratch,
        "XDG_CACHE_HOME": scratch, "TMPDIR": scratch,
    }
    result = subprocess.run([str(probe), str(egl), str(gles)], env=environment,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    sys.stdout.write(result.stdout)
    modules = {value.resolve() for value in [probe, egl, gles]}
    modules.update((egl.parent / name).resolve() for name in ["libvk_swiftshader.so", "libvulkan.so.1", "libVkICD_mock_icd.so"])
    modules.update((glib.parent / name).resolve() for name in ["libglib-2.0.so.0", "libgobject-2.0.so.0", "libgmodule-2.0.so.0", "libgio-2.0.so.0", "libz.so.1"])
    aliases = {}

    def digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").digest()

    def declared_module(path):
        if path in modules:
            return path
        if path not in aliases:
            aliases[path] = next((candidate for candidate in modules
                                  if path.name.endswith(candidate.name)
                                  and path.is_file() and candidate.is_file()
                                  and path.stat().st_size == candidate.stat().st_size
                                  and digest(path) == digest(candidate)), None)
        return aliases[path]

    for module, address in re.findall(r"\[DEBUG-native-graphics\] frame ([^\r\n]+) (0x[0-9a-f]+)", result.stdout)[:24]:
        binary = declared_module(Path(module).resolve())
        if binary is None:
            continue
        print("[DEBUG-native-graphics] module " + binary.name)
        symbols = subprocess.run([str(symbolizer), "--obj=" + str(binary), "--demangle", "--functions=linkage", "--inlines", address],
                                 env=environment, capture_output=True, text=True)
        for line in symbols.stdout.splitlines()[:20]:
            if line:
                print("[DEBUG-native-graphics] symbol " + line)
        if symbols.returncode:
            print(f"[DEBUG-native-graphics] symbolizer exit {symbols.returncode}")
    print(f"[DEBUG-native-graphics] exit {result.returncode}", flush=True)
    raise SystemExit(result.returncode)

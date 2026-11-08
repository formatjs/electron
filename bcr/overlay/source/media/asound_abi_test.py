# SPDX-License-Identifier: MIT
"""Compare the pinned SDK link interface with its real ALSA runtime."""

from pathlib import Path
import struct
import sys


def require(condition, check):
    if not condition:
        raise ValueError("check failed: asound_abi " + check)


def sections(path):
    data = Path(path).read_bytes()
    require(data[:6] == b"\x7fELF\x02\x01", "declared ELF64 little endian inputs")
    offset = struct.unpack_from("<Q", data, 40)[0]
    size, count, names = struct.unpack_from("<HHH", data, 58)
    headers = [struct.unpack_from("<IIQQQQIIQQ", data, offset + index * size) for index in range(count)]
    header = headers[names]
    strings = data[header[4]:header[4] + header[5]]
    return {strings[header[0]:].split(b"\0", 1)[0].decode(): data[header[4]:header[4] + header[5]] for header in headers}


require(len(sys.argv) == 3, "declared SDK and runtime inputs")
sdk, runtime = [sections(path) for path in sys.argv[1:]]
require(".text" not in sdk and bool(runtime.get(".text")), "runtime supplies code absent from SDK interface")
for name in [".dynsym", ".dynstr", ".gnu.version", ".gnu.version_d", ".note.gnu.build-id"]:
    require(name in sdk and sdk[name] == runtime.get(name), "SDK runtime symbol version and build identity")

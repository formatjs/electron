# SPDX-License-Identifier: MIT
"""Deterministic NSS module integrity metadata using original NSS arithmetic."""

import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile


def nonce(q, private, digest):
    """RFC 6979 section 3.2, SHA-256 and a 256-bit subgroup."""
    if q.bit_length() != 256 or not 0 < private < q or len(digest) != 32:
        raise ValueError("Expected NSS DSA-2048/SHA-256 parameters")
    seed = private.to_bytes(32, "big") + (int.from_bytes(digest, "big") % q).to_bytes(32, "big")
    key, value = b"\0" * 32, b"\1" * 32
    for marker in (b"\0", b"\1"):
        key = hmac.digest(key, value + marker + seed, "sha256")
        value = hmac.digest(key, value, "sha256")
    while True:
        value = hmac.digest(key, value, "sha256")
        candidate = int.from_bytes(value, "big")
        if 0 < candidate < q:
            return value
        key = hmac.digest(key, value + b"\0", "sha256")
        value = hmac.digest(key, value, "sha256")


def parameters(source):
    result = []
    for name in ("prime2", "subprime2", "base2"):
        match = re.search(r"static const unsigned char " + name + r"\[\] = \{([^}]+)\};", source)
        if not match:
            raise ValueError("Original NSS DSA parameters missing")
        result.append(bytes(int(part.strip(), 16) for part in match[1].split(",") if part.strip()))
    if int.from_bytes(result[0], "big").bit_length() != 2048:
        raise ValueError("Expected original NSS DSA-2048 parameters")
    return result


def generate(tool, source, module, output, libraries):
    tool, source, module, output = [Path(path).absolute() for path in (tool, source, module, output)]
    values = parameters(source.read_text())
    q = int.from_bytes(values[1], "big")
    # Public build key; NSS .chk files carry their own public key.
    private = 1 + int.from_bytes(hashlib.sha256(b"electron native NSS module integrity v1").digest(), "big") % (q - 1)
    seeds = private.to_bytes(32, "big") + nonce(q, private, hashlib.sha256(module.read_bytes()).digest())
    environment = {"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "LD_LIBRARY_PATH": ":".join(sorted({str(Path(path).absolute().parent) for path in libraries}))}
    results = []
    for repeat in (False, True):
        with tempfile.TemporaryDirectory(prefix="NSS integrity repeat " if repeat else "nss-integrity-") as directory:
            root = Path(directory)
            data = root / ("relocated module.so" if repeat else "module.so")
            shutil.copyfile(module, data)
            os.utime(data, (918273645 if repeat else 123456789,) * 2)
            params = root / "params.bin"
            params.write_bytes(b"".join(struct.pack(">I", len(value)) + value for value in values))
            seed_file = root / "seeds.bin"
            seed_file.write_bytes(seeds)
            result = root / "module.chk"
            subprocess.run([str(tool), str(params), str(seed_file), str(data), str(result)], env=environment, check=True)
            results.append(result.read_bytes())
    if results[0] != results[1]:
        raise ValueError("NSS integrity output differs across paths and mtimes")
    output.write_bytes(results[0])


if __name__ == "__main__":
    generate(*sys.argv[1:5], sys.argv[5:])

# SPDX-License-Identifier: MIT
"""Stage immutable inputs, repair relative ELF search paths, verify closure."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile


def _relative(path):
    parsed = PurePosixPath(path)
    if (not path or parsed.is_absolute() or parsed.as_posix() != path or
            "\\" in path or ":" in path or path == "." or ".." in parsed.parts):
        raise ValueError("Invalid runtime path: " + path)
    return path


def _digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").digest()


def assemble(manifest, directory, mtime=0):
    root = directory / "runtime"
    root.mkdir()
    patchelf = str(Path(manifest["patchelf"]).resolve())
    environment = {"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}

    def patch(*arguments):
        return subprocess.run([patchelf, *arguments], check=True, capture_output=True,
                              text=True, env=environment).stdout.strip()

    entries = sorted(manifest["entries"], key=lambda entry: entry["path"])
    if len({entry["path"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate runtime path")
    executables = set(manifest["executables"])
    host_abi = set(manifest["host_abi"])
    if any("/" in name or not name for name in host_abi):
        raise ValueError("Host ABI must contain plain SONAMEs")
    records, providers, originals = [], {}, []
    for entry in entries:
        path = _relative(entry["path"])
        source = Path(entry["source"])
        digest = _digest(source)
        expected = manifest.get("expected_sha256", {}).get(path)
        if expected and digest.hex() != expected:
            raise ValueError("Pinned runtime input changed: " + path)
        originals.append((source, digest))
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        os.utime(destination, (mtime, mtime))
        with destination.open("rb") as stream:
            header = stream.read(20)
        elf = header.startswith(b"\x7fELF")
        if path in executables or entry["library"]:
            if not elf:
                raise ValueError("Runtime program/library is not ELF: " + path)
        if not elf:
            continue
        if (entry["library"] and Path(path).parent.as_posix() != "lib") or (not entry["library"] and Path(path).parent.as_posix() != "."):
            raise ValueError("Runtime ELF must be at the root or directly in lib: " + path)
        if len(header) != 20 or header[4:6] != b"\x02\x01" or struct.unpack_from("<H", header, 18)[0] != 62:
            raise ValueError("Expected Linux x86_64 ELF: " + path)
        elf_type = struct.unpack_from("<H", header, 16)[0]
        if elf_type not in (2, 3) or (path not in executables and elf_type != 3):
            raise ValueError("Expected runtime executable or shared object: " + path)
        interpreter = patch("--print-interpreter", str(destination)) if path in executables else ""
        if path in executables and interpreter not in ("/lib64/ld-linux-x86-64.so.2", "/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"):
            raise ValueError("Runtime ELF uses a nonportable interpreter: " + path)
        soname = patch("--print-soname", str(destination))
        if path not in executables:
            if soname != destination.name:
                raise ValueError("Runtime SONAME differs from destination: " + path)
        if soname:
            if "/" in soname or soname in providers or soname in host_abi:
                raise ValueError("Ambiguous runtime SONAME: " + soname)
            providers[soname] = path
        rpath = "$ORIGIN:$ORIGIN/.." if entry["library"] else "$ORIGIN:$ORIGIN/lib"
        patch("--set-rpath", rpath, str(destination))
        if patch("--print-rpath", str(destination)) != rpath:
            raise ValueError("Runtime ELF search path was not normalized: " + path)
        needed = patch("--print-needed", str(destination)).splitlines()
        if any("/" in name or not name for name in needed):
            raise ValueError("Runtime ELF contains a nonportable dependency: " + path)
        records.append({"path": path, "soname": soname, "needed": needed, "rpath": rpath, "interpreter": interpreter})
    missing = sorted({name for record in records for name in record["needed"] if name not in providers and name not in host_abi})
    if missing:
        raise ValueError("Unbundled runtime dependencies: " + ", ".join(missing))
    if not executables <= {record["path"] for record in records}:
        raise ValueError("Runtime executable is missing")
    paths = [entry["path"] for entry in entries]
    integrity = manifest.get("nss_integrity", {})
    if integrity:
        libraries = [str(root / record["path"]) for record in records if record["soname"]]
        for module in sorted(integrity["modules"]):
            path = "lib/" + _relative(module)
            checksum = path.removesuffix(".so") + ".chk"
            if path not in paths or checksum in paths:
                raise ValueError("NSS integrity requires distinct declared module paths")
            # NSS verifies final module bytes, including repaired ELF search paths.
            subprocess.run([sys.executable, "-I", "-B", integrity["script"], integrity["tool"],
                            integrity["parameters"], str(root / path), str(root / checksum), *libraries],
                           env=environment, check=True)
            paths.append(checksum)
    archive = directory / "runtime.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as output:
        for path in sorted(paths):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info._compresslevel = 1
            info.external_attr = (stat.S_IFREG | (0o755 if path in executables else 0o644)) << 16
            with (root / path).open("rb") as source, output.open(info, "w", force_zip64=True) as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
    for source, digest in originals:
        if _digest(source) != digest:
            raise ValueError("Runtime assembly modified an input")
    return archive, {"elf": records, "host_abi": sorted({name for record in records for name in record["needed"] if name in host_abi})}


def run(manifest):
    with tempfile.TemporaryDirectory(prefix="electron-runtime-") as first, tempfile.TemporaryDirectory(prefix="electron runtime repeat ") as second:
        archive, report = assemble(manifest, Path(first), mtime=123456789)
        repeated, repeated_report = assemble(manifest, Path(second), mtime=918273645)
        if report != repeated_report or _digest(archive) != _digest(repeated):
            raise ValueError("Runtime assembly differs across staging roots")
        shutil.copyfile(archive, manifest["archive"])
        Path(manifest["report"]).write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    run(json.loads(Path(sys.argv[1]).read_text()))

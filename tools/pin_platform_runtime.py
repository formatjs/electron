# SPDX-License-Identifier: MIT
"""Capture an SDK-matched Debian ELF closure without executing library code."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.request


def ar_members(data):
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("Expected Debian ar archive")
    result, offset = {}, 8
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[58:] != b"`\n":
            raise ValueError("Invalid Debian ar member")
        name = header[:16].decode("ascii").strip().removesuffix("/")
        size = int(header[48:58])
        payload = data[offset + 60:offset + 60 + size]
        if len(payload) != size or name in result:
            raise ValueError("Truncated or duplicate Debian ar member")
        result[name] = payload
        offset += 60 + size + size % 2
    return result


def fields(text):
    return dict(line.split(": ", 1) for line in text.splitlines() if ": " in line and not line.startswith(" "))


def payload_files(data, prefix):
    members = ar_members(data)
    candidates = [value for name, value in members.items() if name.startswith(prefix + ".tar.")]
    if len(candidates) != 1:
        raise ValueError("Expected one Debian payload")
    with tarfile.open(fileobj=io.BytesIO(candidates[0])) as archive:
        return {entry.name.removeprefix("./"): archive.extractfile(entry).read()
                for entry in archive.getmembers() if entry.isfile()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sdk", "manifest", "cache", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--architecture", choices=("amd64", "arm64"), default="amd64",
                        help="Debian SDK target architecture; the manifest must match")
    args = parser.parse_args()
    sdk = args.sdk.resolve()
    manifest = json.loads(args.manifest.read_text())
    # Unmarked captures are existing AMD64 inventories.
    if manifest.get("architecture", "amd64") != args.architecture:
        raise ValueError("Runtime manifest architecture differs from requested SDK")
    manifest["architecture"] = args.architecture
    triple = {"amd64": "x86_64-linux-gnu", "arm64": "aarch64-linux-gnu"}[args.architecture]
    args.cache.mkdir(parents=True, exist_ok=True)
    owners = {}
    for path in (sdk / "debian").glob("*/DEBIAN/md5sums"):
        package = fields(path.with_name("control").read_text())
        for line in path.read_text().splitlines():
            digest, interface = line.split(maxsplit=1)
            owners[interface.strip()] = (package, digest)
    packages = {}
    pending, added = list(args.root), []
    while pending:
        soname = pending.pop()
        if soname in manifest["libraries"] or soname in manifest["system_libraries"]:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", soname):
            raise ValueError("Invalid library SONAME")
        interface = next((sdk / directory / soname for directory in ("usr/lib/" + triple, "lib/" + triple)
                          if (sdk / directory / soname).exists()), None)
        if interface is None:
            raise ValueError("SDK library unavailable: " + soname)
        for _ in range(40):
            if not interface.is_symlink():
                break
            target = os.readlink(interface)
            interface = sdk / target.lstrip("/") if target.startswith("/") else interface.parent / target
        else:
            raise ValueError("SDK library symlink cycle")
        relative = interface.resolve().relative_to(sdk).as_posix()
        package, expected_md5 = owners[relative]
        name, version, architecture = (package[key] for key in ("Package", "Version", "Architecture"))
        if architecture != args.architecture:
            raise ValueError("SDK package architecture differs from requested target")
        if name not in packages:
            source = package.get("Source", name).split(" ", 1)[0]
            filename = name + "_" + version.split(":", 1)[-1] + "_" + architecture + ".deb"
            relative_url = "pool/main/" + (source[:4] if source.startswith("lib") else source[0]) + "/" + source + "/" + filename
            urls = ["https://archive.debian.org/debian/" + relative_url,
                    "https://deb.debian.org/debian/" + relative_url,
                    "https://snapshot.debian.org/archive/debian/20250129T203412Z/" + relative_url]
            archive = args.cache / filename
            if not archive.exists():
                for url in urls:
                    try:
                        with urllib.request.urlopen(url, timeout=30) as response:
                            data = response.read(32 * 1024**2 + 1)
                        if len(data) > 32 * 1024**2:
                            raise ValueError("Debian package exceeds capture limit")
                        ar_members(data)
                        archive.write_bytes(data)
                        break
                    except (OSError, ValueError):
                        continue
                else:
                    raise ValueError("SDK package unavailable: " + filename)
            data = archive.read_bytes()
            control = fields(payload_files(data, "control")["control"].decode())
            if (control["Package"], control["Version"], control["Architecture"]) != (name, version, architecture):
                raise ValueError("Debian package identity differs from SDK metadata")
            packages[name] = payload_files(data, "data")
            record = dict(url=urls[0], urls=urls, sha256=hashlib.sha256(data).hexdigest())
            if not any(row["sha256"] == record["sha256"] for row in manifest["packages"]):
                manifest["packages"].append(record)
        binary = packages[name][relative]
        if hashlib.md5(binary).hexdigest() != expected_md5:
            raise ValueError("Runtime library differs from original SDK package: " + soname)
        elf = args.cache / (soname + ".elf")
        elf.write_bytes(binary)
        dynamic = subprocess.check_output(["readelf", "-d", str(elf)], text=True)
        declared_soname = re.search(r"\(SONAME\).*\[([^\]]+)\]", dynamic)
        if not declared_soname or declared_soname[1] != soname:
            raise ValueError("Runtime SONAME differs from SDK interface")
        needed = re.findall(r"\(NEEDED\).*\[([^\]]+)\]", dynamic)
        record = next(row for row in manifest["packages"] if "/" + name + "_" in row["url"])
        manifest["libraries"][soname] = dict(package=name, interface=relative, needed=needed, url=record["url"], md5=expected_md5)
        pending.extend(needed)
        added.append(soname)
    manifest["root_libraries"] = sorted(set(manifest["root_libraries"]) | set(args.root))
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(dict(added=sorted(added), packages=len(packages))))


if __name__ == "__main__":
    main()

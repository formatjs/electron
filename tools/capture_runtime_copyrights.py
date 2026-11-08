# SPDX-License-Identifier: MIT
"""Pin Debian runtime notices, including copyright packages referenced by links."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import io
import posixpath
import tarfile
import urllib.request

from pin_platform_runtime import ar_members, fields, payload_files


def capture(manifest, runtime_root, sdk, cache):
    cache.mkdir(parents=True, exist_ok=True)
    downloaded = {}

    def source_notice(name):
        directory = runtime_root / "packages" / name / "root"
        notice = directory / "usr/share/doc" / name / "copyright"
        if notice.is_file():
            relative = notice.resolve().relative_to(directory.resolve()).as_posix()
            return name, relative, notice.read_bytes()
        doc = directory / "usr/share/doc" / name
        if not doc.is_symlink():
            raise ValueError("Runtime package lacks copyright: " + name)
        owner = os.readlink(doc)
        if not owner or Path(owner).name != owner or owner in (".", ".."):
            raise ValueError("Unexpected runtime copyright link: " + name)
        if owner not in downloaded:
            control = fields((sdk / "debian" / owner / "DEBIAN/control").read_text())
            version, architecture = control["Version"], control["Architecture"]
            source = control.get("Source", owner).split(" ", 1)[0]
            filename = owner + "_" + version.split(":", 1)[-1] + "_" + architecture + ".deb"
            relative = "pool/main/" + (source[:4] if source.startswith("lib") else source[0]) + "/" + source + "/" + filename
            urls = ["https://archive.debian.org/debian/" + relative,
                    "https://deb.debian.org/debian/" + relative,
                    "https://snapshot.debian.org/archive/debian/20250129T203412Z/" + relative]
            archive = cache / filename
            if not archive.exists():
                for url in urls:
                    try:
                        with urllib.request.urlopen(url, timeout=30) as response:
                            raw = response.read(4 * 1024**2 + 1)
                        if len(raw) > 4 * 1024**2:
                            raise ValueError("Copyright package exceeds capture limit")
                        ar_members(raw)
                        archive.write_bytes(raw)
                        break
                    except (OSError, ValueError):
                        continue
                else:
                    raise ValueError("Pinned copyright package unavailable")
            raw = archive.read_bytes()
            identity = fields(payload_files(raw, "control")["control"].decode())
            if any(identity[key] != control[key] for key in ("Package", "Version", "Architecture")):
                raise ValueError("Copyright package differs from SDK identity")
            data = payload_files(raw, "data")
            relative = "usr/share/doc/" + owner + "/copyright"
            checksums = dict(reversed(line.split(maxsplit=1)) for line in (sdk / "debian" / owner / "DEBIAN/md5sums").read_text().splitlines())
            if hashlib.md5(data[relative]).hexdigest() != checksums[relative]:
                raise ValueError("Copyright text differs from pinned SDK metadata")
            record = {"url": urls[0], "urls": urls, "sha256": hashlib.sha256(raw).hexdigest()}
            existing = [row for row in manifest["packages"] if "/" + owner + "_" in row["url"]]
            if existing and existing[0]["sha256"] != record["sha256"]:
                raise ValueError("Copyright package changed")
            if not existing:
                manifest["packages"].append(record)
            downloaded[owner] = (owner, relative, data[relative])
        return downloaded[owner]

    notices = {}
    for name in sorted({library["package"] for library in manifest["libraries"].values()}):
        owner, path, content = source_notice(name)
        notices[name] = {"package": owner, "path": path, "sha256": hashlib.sha256(content).hexdigest()}
    manifest["copyrights"] = notices
    filename = "base-files_11.1+deb11u11_amd64.deb"
    relative_url = "pool/main/b/base-files/" + filename
    urls = ["https://archive.debian.org/debian/" + relative_url,
            "https://snapshot.debian.org/archive/debian/20250129T203412Z/" + relative_url]
    archive = cache / filename
    if not archive.exists():
        with urllib.request.urlopen(urls[0], timeout=30) as response:
            raw = response.read(4 * 1024**2 + 1)
        if len(raw) > 4 * 1024**2:
            raise ValueError("Common license package exceeds capture limit")
        ar_members(raw)
        archive.write_bytes(raw)
    raw = archive.read_bytes()
    identity = fields(payload_files(raw, "control")["control"].decode())
    if (identity["Package"], identity["Version"], identity["Architecture"]) != ("base-files", "11.1+deb11u11", "amd64"):
        raise ValueError("Unexpected common license package identity")
    record = {"url": urls[0], "urls": urls, "sha256": hashlib.sha256(raw).hexdigest()}
    existing = [row for row in manifest["packages"] if "/base-files_" in row["url"]]
    if existing and existing[0]["sha256"] != record["sha256"]:
        raise ValueError("Common license package changed")
    if not existing:
        manifest["packages"].append(record)
    data = payload_files(raw, "data")
    members = ar_members(raw)
    payload = next(value for name, value in members.items() if name.startswith("data.tar."))
    with tarfile.open(fileobj=io.BytesIO(payload)) as contents:
        for entry in contents.getmembers():
            path = entry.name.removeprefix("./")
            if path.startswith("usr/share/common-licenses/") and entry.issym():
                target = posixpath.normpath(posixpath.join(posixpath.dirname(path), entry.linkname))
                if not target.startswith("usr/share/common-licenses/") or target not in data:
                    raise ValueError("Unexpected common license link")
                data[path] = data[target]
    manifest["common_licenses"] = {
        Path(path).name: {"package": "base-files", "path": path, "sha256": hashlib.sha256(content).hexdigest()}
        for path, content in sorted(data.items()) if path.startswith("usr/share/common-licenses/")
    }
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "runtime-root", "sdk", "cache", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = capture(json.loads(args.manifest.read_text()), args.runtime_root, args.sdk, args.cache)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"packages": len(result["packages"]), "copyrights": len(result["copyrights"])}))


if __name__ == "__main__":
    main()

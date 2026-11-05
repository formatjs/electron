# SPDX-License-Identifier: MIT
"""Build a portable Electron app ZIP from declared inputs only."""

import argparse
import json
import plistlib
import posixpath
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath


def safe_path(name):
    path = PurePosixPath(name)
    if (not name or name.startswith("/") or "\\" in name or ":" in name
            or any(part in ("", ".", "..") for part in name.rstrip("/").split("/"))):
        raise ValueError(f"Unsafe archive path: {name!r}")
    return path.as_posix()


def archive_info(name, mode=0o644):
    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 3
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = mode << 16
    return entry


def expand_files(manifest):
    files = {}
    for destination, filename in sorted(manifest.items()):
        safe_path(destination)
        source = Path(filename)
        directory = source.is_dir()
        candidates = source.rglob("*") if directory else [source]
        for candidate in sorted(candidates):
            if directory and candidate.is_symlink():
                if candidate.is_dir():
                    raise ValueError(f"App tree requires materialized dependencies: {candidate}")
            if candidate.is_dir():
                continue
            name = destination + "/" + candidate.relative_to(source).as_posix() if directory else destination
            if name in files:
                raise ValueError(f"Duplicate app path: {name}")
            files[name] = candidate
    return files


def package(runtime, platform, app_manifest, output, product_name, bundle_id):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _.-]*", product_name) or product_name.endswith((".", " ")):
        raise ValueError("product_name must start with a letter and contain portable filename characters")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*(?:\.[A-Za-z0-9-]+)+", bundle_id):
        raise ValueError("bundle_id must be a reverse DNS identifier")
    if platform not in {"linux_amd64", "linux_arm64", "darwin_arm64", "windows_amd64", "windows_arm64"}:
        raise ValueError(f"Unsupported platform: {platform}")
    app_files = expand_files(json.loads(Path(app_manifest).read_text(encoding="utf-8")))
    for name in app_files:
        safe_path(name)
    if "package.json" not in app_files:
        raise ValueError("App requires package.json")
    metadata = json.loads(Path(app_files["package.json"]).read_text(encoding="utf-8"))
    if safe_path(metadata["main"]) not in app_files:
        raise ValueError("App main missing from declared files")
    mac = platform.startswith("darwin_")
    windows = platform.startswith("windows_")
    resources = product_name + ".app/Contents/Resources" if mac else "resources"
    original_main = "Electron.app/Contents/MacOS/Electron" if mac else "electron.exe" if windows else "electron"
    seen = set()
    directories = set()
    # Windows and default macOS volumes compare paths without case sensitivity.
    casefold = mac or windows

    def reserve(name):
        normalized = safe_path(name)
        key = normalized.casefold() if casefold else normalized
        if key in seen:
            raise ValueError(f"Duplicate archive path: {name}")
        parts = key.split("/")[:-1]
        parents = {"/".join(parts[:length]) for length in range(1, len(parts) + 1)}
        if key in directories or parents.intersection(seen):
            raise ValueError(f"Archive file/directory collision: {name}")
        seen.add(key)
        directories.update(parents)
        return normalized

    with zipfile.ZipFile(runtime) as source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as destination:
        if original_main not in source.namelist():
            raise ValueError(f"Runtime missing executable: {original_main}")
        for original in sorted(source.infolist(), key=lambda entry: entry.filename):
            name = safe_path(original.filename)
            if original.is_dir():
                continue
            if mac:
                if name.startswith("Electron.app/"):
                    name = product_name + ".app/" + name[len("Electron.app/"):]
                if "/_CodeSignature/" in name:
                    continue
                if name == product_name + ".app/Contents/MacOS/Electron":
                    name = product_name + ".app/Contents/MacOS/" + product_name
            elif name == original_main:
                name = product_name + (".exe" if windows else "")
            elif windows and name == "electron_wer.dll":
                name = product_name + "_wer.dll"
            if name == resources + "/default_app.asar":
                continue
            if name.startswith(resources + "/app/") or name in (resources + "/app.asar", resources + "/app"):
                raise ValueError("Runtime already contains app payload")
            reserve(name)
            mode = original.external_attr >> 16
            if stat.S_ISLNK(mode):
                target = source.read(original).decode("utf-8")
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                if target.startswith("/") or "\\" in target or ":" in target or resolved == ".." or resolved.startswith("../"):
                    raise ValueError(f"Unsafe archive symlink: {name} -> {target}")
                destination.writestr(archive_info(name, stat.S_IFLNK | 0o777), target)
            elif mac and name.endswith("/Info.plist"):
                values = plistlib.loads(source.read(original))
                if name == product_name + ".app/Contents/Info.plist":
                    values.update(CFBundleDisplayName=product_name, CFBundleName=product_name, CFBundleIdentifier=bundle_id, CFBundleExecutable=product_name)
                elif "/Electron Helper" in name:
                    old_id = values.get("CFBundleIdentifier", "com.github.Electron.helper")
                    values["CFBundleIdentifier"] = bundle_id + old_id.removeprefix("com.github.Electron")
                    values["CFBundleDisplayName"] = product_name + " Helper"
                    values["CFBundleName"] = product_name + " Helper"
                destination.writestr(archive_info(name, stat.S_IFREG | 0o644), plistlib.dumps(values, sort_keys=True))
            else:
                permissions = 0o755 if mode & 0o111 or original.filename == original_main else 0o644
                with source.open(original) as reader, destination.open(archive_info(name, stat.S_IFREG | permissions), "w", force_zip64=True) as writer:
                    shutil.copyfileobj(reader, writer, length=1024 * 1024)
        for name, filename in sorted(app_files.items()):
            output_name = reserve(resources + "/app/" + name)
            mode = stat.S_IFREG | (0o755 if Path(filename).stat().st_mode & 0o111 else 0o644)
            with Path(filename).open("rb") as reader, destination.open(archive_info(output_name, mode), "w", force_zip64=True) as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime", "platform", "app-manifest", "output", "product-name", "bundle-id"):
        parser.add_argument("--" + name, required=True)
    package(**vars(parser.parse_args()))


if __name__ == "__main__":
    main()

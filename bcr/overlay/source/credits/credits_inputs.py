# SPDX-License-Identifier: MIT
"""Capture the original license scanner's source-only view."""

import json
from pathlib import Path


def discover(licenses, root):
    root = Path(root)
    directories = licenses.FindThirdPartyDirs(str(root))
    files, records = {"LICENSE"}, []
    for directory in directories:
        for name in licenses.METADATA_FILE_NAMES | {licenses.ADDITIONAL_PATHS_FILENAME}:
            path = root / directory / name
            if path.is_file():
                files.add(path.relative_to(root).as_posix())
        try:
            metadata, _ = licenses.ParseDir(directory, str(root))
        except licenses.LicenseError:
            continue
        for entry in metadata:
            paths = [Path(path).relative_to(root).as_posix() for path in entry["License File"]]
            files.update(paths)
            records.append({
                "directory": directory,
                "name": entry["Name"],
                "url": entry["URL"],
                "shipped": entry["Shipped"],
                "licenses": paths,
            })
    return directories, sorted(files), sorted(records, key=lambda entry: json.dumps(entry, sort_keys=True))

# SPDX-License-Identifier: MIT
"""Capture original font and XML libraries needed by the Skia/content closure."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from native_graph import capture_library

ROOTS = ["//third_party/freetype:freetype", "//third_party/harfbuzz-ng:harfbuzz-ng", "//third_party/libpng:libpng", "//third_party/libxml:libxml"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
PINS = {"freetype": "d3668e00da732654b50e4e81f982544ed6e26390", "harfbuzz": "7d936359a27abb2d7cb14ecc102463bb15c11843"}


def capture(graph, digest, chromium, freetype, harfbuzz):
    external = {"//third_party/icu:icuuc": "@electron_icu_sources//:icu", "//third_party/zlib:zlib": "@electron_v8_support_sources//:zlib"}
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        if not label.startswith(("//third_party/freetype:", "//third_party/harfbuzz-ng:", "//third_party/libpng:", "//third_party/libxml:")):
            raise ValueError("Untranslated font/XML dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    for revision in PINS.values():
        if revision not in (chromium / "DEPS").read_text():
            raise ValueError("Font DEPS pin changed")
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}
    roots = {"third_party/freetype/src": freetype, "third_party/harfbuzz-ng/src": harfbuzz}

    def physical(path):
        for prefix, root in roots.items():
            if path.startswith(prefix + "/"):
                return root / path[len(prefix) + 1:]
        return chromium / path

    files, headers, textual = set(), {}, {}
    for directory in ["third_party/freetype", "third_party/harfbuzz-ng", "third_party/libpng", "third_party/libxml"]:
        inventory = set()
        for prefix, root in [(directory, chromium / directory)] + [(prefix, root) for prefix, root in roots.items() if prefix.startswith(directory + "/")]:
            inventory.update(prefix + "/" + path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".hh", ".hpp", ".inc", ".inl", ".c"))
        if not inventory:
            raise ValueError("Missing font/XML header inventory")
        headers[directory] = sorted(path for path in inventory if not path.endswith(".c"))
        textual[directory] = sorted(path for path in inventory if path.endswith(".c"))
        files.update(inventory)

    def input_file(path):
        if not path.startswith("//") or path.startswith("//out/"):
            raise ValueError("Unexpected font/XML input: " + path)
        files.add(path[2:])

    libraries = {}
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64" or target["type"] not in ("group", "source_set", "static_library"):
            raise ValueError("Unexpected font/XML target configuration")
        record = dict(name=names[label], kind=target["type"], gn_deps=target.get("deps", []))
        libraries[label] = capture_library(graph, target, record, input_file, label)
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original font/XML source: " + path)
    return dict(roots=ROOTS, graph_sha256=digest, source_revisions=PINS, names=names, libraries=libraries, headers=headers, textual_headers=textual, files=sorted(files), external=external, toolchain_deps=sorted(TOOLCHAIN))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "freetype-root", "harfbuzz-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, args.freetype_root, args.harfbuzz_root)
    args.output.write_text(json.dumps(profile, indent=2) + "\n")


if __name__ == "__main__":
    main()

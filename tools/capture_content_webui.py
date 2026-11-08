# SPDX-License-Identifier: MIT
"""Capture original content WebUI producers with existing native providers."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import capture_ui
from capture_mojo import SCRIPTS as MOJO_SCRIPTS
from native_graph import load_profiles


def capture(graph, digest, chromium, node_modules, profiles):
    additional = [("ui", "ui"), ("platform", "platform")]
    external, _ = load_profiles(profiles, capture_ui.PROVIDERS + additional)
    scripts = capture_ui.SCRIPTS - MOJO_SCRIPTS - {"//build/write_buildflag_header.py"}
    targets, seen, pending = graph["targets"], set(), ["//content:content"]
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in capture_ui.TOOLCHAIN:
            continue
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    roots = sorted(label for label in seen if targets[label].get("script") in scripts)
    if not roots:
        raise ValueError("Missing original content WebUI producers")
    profile = capture_ui.capture(graph, digest, chromium, node_modules, profiles,
                                 roots=roots, additional_profiles=additional, reuse_providers=True)
    if any(library[language] for library in profile["libraries"].values()
           for language in ("srcs", "c_srcs", "asm_srcs")):
        raise ValueError("Content WebUI must reuse native library providers")
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "node-modules-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(),
                      args.chromium_root, args.node_modules_root, args.profiles)
    args.output.write_text(json.dumps(profile, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Capture Electron app WebUI producers with existing native providers."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import capture_ui
from capture_mojo import SCRIPTS as MOJO_SCRIPTS
from native_graph import load_profiles


def capture(graph, digest, chromium, node_modules, profiles, *, root="//electron:electron_app"):
    additional = [("ui", "ui"), ("platform", "platform")]
    external, _ = load_profiles(profiles, capture_ui.PROVIDERS + additional)
    external = {label: owner for label, owner in external.items() if not owner.startswith("@electron_content_webui_sources//:")}
    scripts = capture_ui.SCRIPTS - MOJO_SCRIPTS - {"//build/write_buildflag_header.py"}
    targets, seen, pending = graph["targets"], set(), [root]
    while pending:
        label = pending.pop()
        if label in seen or label in capture_ui.TOOLCHAIN:
            continue
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    roots = sorted(label for label in seen if label not in external and targets[label].get("script") in scripts)
    if not roots:
        raise ValueError("Missing original content WebUI producers")
    profile = capture_ui.capture(graph, digest, chromium, node_modules, profiles,
                                 roots=roots, additional_profiles=additional, reuse_providers=True,
                                 current_repository="content_webui")
    if any(library[language] for library in profile["libraries"].values()
           for language in ("srcs", "c_srcs", "asm_srcs")):
        raise ValueError("Content WebUI must reuse native library providers")
    profile["capture_root"] = root
    use_real_credits(profile)
    return profile


def use_real_credits(profile):
    label = "//components/resources:about_credits"
    path = "//out/bazel-import/gen/components/resources/about_credits.html"
    if label not in profile["copies"] and label not in profile["actions"]:
        raise ValueError("Missing original credits producer")
    profile["copies"].pop(label, None)
    profile["actions"].pop(label, None)
    profile["external"][label] = "@electron//source/credits:credits"
    profile["external_files"][path] = "@electron//source/credits:about_credits.html"
    for action in profile["actions"].values():
        if label in action["ordering_deps"]:
            if path not in action["inputs"]:
                raise ValueError("Credits ordering edge lacks a declared HTML input")
            action["ordering_deps"].remove(label)
    profile["credits_adapter"] = {
        "original": label,
        "replacement": "@electron//source/credits:generate",
        "reason": "Replace the development sample with original Chromium credits for distribution",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "node-modules-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--root", default="//electron:electron_app")
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(),
                      args.chromium_root, args.node_modules_root, args.profiles, root=args.root)
    args.output.write_text(json.dumps(profile, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()

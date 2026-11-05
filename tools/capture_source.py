# SPDX-License-Identifier: MIT
"""Capture Electron metadata using Chromium's validated GN graph serializer."""
import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("chromium-tools", "source-root", "llvm-root", "rust-root", "gn", "runtime-deps", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    source = args.chromium_tools / "capture_native_graph.py"
    spec = importlib.util.spec_from_file_location("chromium_capture", source)
    capture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capture)
    project = json.loads((args.source_root / "out/bazel-import/project.json").read_text(encoding="utf-8"))
    project = capture.target_closure(project, ["//electron:electron"])
    replacements = [(str(args.llvm_root), "$LLVM_ROOT"), (str(args.rust_root), "$RUST_ROOT"), (str(args.source_root), "$SOURCE_ROOT")]
    graph = capture.capture(project, json.loads(args.runtime_deps.read_text(encoding="utf-8")), args.source_root, replacements)
    configuration = (args.source_root / "out/bazel-import/args.gn").read_text(encoding="utf-8")
    for old, new in replacements:
        configuration = configuration.replace(old, new)
    patch_config = json.loads((args.source_root / "electron/patches/config.json").read_text(encoding="utf-8"))
    remaining = [entry["patch_dir"].split("/")[-1] for entry in patch_config if entry["patch_dir"].split("/")[-1] not in {"chromium", "node", "v8"}]
    graph["provenance"] = {
        "chromium_revision": "7efca501bfcc84657ba2921a852e98ce1fb37641",
        "electron_version": "39.0.0",
        "gn_version": subprocess.check_output([str(args.gn), "--version"], text=True).strip(),
        "gn_sha256": hashlib.sha256(args.gn.read_bytes()).hexdigest(),
        "capture_tool_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "deps_sha256": hashlib.sha256((args.source_root / "DEPS").read_bytes()).hexdigest(),
        "args_gn": configuration,
        "incomplete_patch_groups": remaining,
        "purpose": "Maintainer GN import metadata; remaining patch stacks and source linkage unfinished",
    }
    payload = json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(payload, mtime=0))
    summary = {
        "provenance": graph["provenance"],
        "graph_sha256": hashlib.sha256(payload).hexdigest(),
        "target_count": len(graph["targets"]),
        "target_types": dict(sorted(Counter(target["type"] for target in graph["targets"].values()).items())),
        "runtime_files": {label: len(files) for label, files in graph["runtime_files"].items()},
        "generated_files": len(graph["generated_files"]),
    }
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    flags = project["targets"]["//base:debugging_buildflags"]["response_file_contents"][1:]
    args.output.with_name("fuses_flags.bzl").write_text('"""From Electron39 Linux AMD64 GN //base:debugging_buildflags."""\n\nDEBUG_FLAGS = ' + json.dumps(flags, indent=4) + "\n", encoding="utf-8")
    print(f"Captured {len(graph['targets'])} targets, {len(payload)} bytes, {args.output.stat().st_size} compressed")


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Capture Node builtin inputs and effective config from the verified GN graph."""
import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "gn-args", "generator", "settings", "inventory"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    graph = json.loads(gzip.decompress(args.graph.read_bytes()))
    config = dict(re.findall(r"(\w+)\s+=\s+(.*?)$", args.gn_args.read_text(), re.MULTILINE))
    if config["target_os"] != '"linux"' or config["target_cpu"] != '"x64"':
        raise ValueError("Expected Linux AMD64 target GN arguments")
    source = ast.parse(args.generator.read_text())
    keys = {node.slice.value for node in ast.walk(source) if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "config" and isinstance(node.slice, ast.Constant)} - {"napi_build_version"}
    settings = {
        "graph_sha256": hashlib.sha256(args.graph.read_bytes()).hexdigest(),
        "generator_sha256": hashlib.sha256(args.generator.read_bytes()).hexdigest(),
        "target_os": "linux",
        "target_cpu": "x64",
        "gn_config": {key: config[key] for key in sorted(keys)},
        "v8_features": json.loads(graph["generated_files"]["//out/bazel-import/v8_features.json"]),
    }
    original = graph["targets"]["//third_party/electron_node:node_js2c_original_fs"]["args"][1:]
    builtins = graph["targets"]["//third_party/electron_node:run_node_js2c"]["args"][4:]
    generated = {name.replace("internal/fs/", "internal/original-fs/").replace("lib/fs.js", "lib/original-fs.js").replace("lib/fs/", "lib/original-fs/") for name in original}
    copied = {name.removeprefix("//third_party/electron_node/") for name in graph["targets"]["//third_party/electron_node:node_js2c_inputs"]["sources"]}
    if set(builtins) != copied | generated:
        raise ValueError("Node builtin inputs differ from generated/copied GN inputs")
    args.settings.write_text(json.dumps(settings, indent=2) + "\n")
    args.inventory.write_text('"""Exact inputs from Electron 39.0.0 Linux GN graph; regenerate with capture_node_inputs.py."""\n\nORIGINAL_FS_INPUTS = ' + json.dumps(original, indent=4) + '\n\nNODE_BUILTIN_INPUTS = ' + json.dumps(sorted(copied), indent=4) + '\n')


if __name__ == "__main__":
    main()

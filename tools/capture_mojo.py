# SPDX-License-Identifier: MIT
"""Capture typed Mojo bindings, original generators and service-manager interfaces."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from native_graph import BUILD, capture_library

ROOTS = ["//mojo/public/cpp/bindings:bindings", "//mojo/public/mojom/base:base", "//services/service_manager/public/mojom:mojom"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
SCRIPTS = {"//mojo/public/tools/" + path for path in ("bindings/validate_typemap_config.py", "bindings/mojom_bindings_generator.py", "mojom/mojom_parser.py", "bindings/validate_ts_typemap_config.py", "bindings/generate_type_mappings.py")}


def capture(graph, graph_digest, chromium, profiles):
    external = {}
    for name, repository in [("base", "base"), ("embedder", "embedder"), ("ipcz", "ipcz"), ("libnode", "libnode"), ("perfetto", "perfetto_native"), ("protobuf", "protobuf"), ("v8_engine", "v8_engine"), ("v8_support", "v8_support"), ("network", "network")]:
        profile = json.loads((profiles / (name + "_inputs.json")).read_text())
        owner = "@electron_" + repository + "_sources//"
        external.update({label: owner + ":" + target for label, target in profile.get("names", {}).items()})
        external.update({label: owner + target if target.startswith(":") else target for label, target in profile.get("external", {}).items()})
        if name == "protobuf":
            external.update({label: owner + ":" + target["name"] for label, target in profile["libraries"].items()})
    network = json.loads((profiles / "network_inputs.json").read_text())
    if network["graph_sha256"] != graph_digest:
        raise ValueError("Expected matching network capture for shared Mojo headers")
    shared_headers = {"//" + path: "@electron_network_sources//:" + path for path in network["headers"]["mojo"]}
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        if not label.startswith(("//mojo/", "//ipc:", "//services/service_manager/public/")):
            raise ValueError("Untranslated typed Mojo dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}
    producers = {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "generated_file"):
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate typed Mojo output")
                producers[output] = label
    files, generated, headers = set(), {}, {}

    def input_file(path):
        if path in shared_headers:
            return
        if path.startswith(BUILD):
            if path in graph["generated_files"]:
                generated[path] = graph["generated_files"][path]
            elif path not in producers:
                raise ValueError("Unowned typed Mojo input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Unexpected typed Mojo input")

    for directory in ("ipc", "services/service_manager/public"):
        inventory = sorted(path.relative_to(chromium).as_posix() for path in (chromium / directory).rglob("*") if path.is_file() and path.suffix in (".h", ".inc", ".inl"))
        if not inventory:
            raise ValueError("Missing original typed Mojo header inventory")
        headers[directory] = inventory
        files.update(inventory)
    actions, libraries, metadata = {}, {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 typed Mojo profile")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind == "action":
            if target["script"] not in SCRIPTS:
                raise ValueError("Untranslated typed Mojo generator")
            inputs = sorted(set(target.get("inputs", []) + target.get("sources", []) + [target["script"]]))
            for path in inputs:
                input_file(path)
            record.update(script=target["script"][2:], inputs=inputs, outputs=target["outputs"], args=target["args"], response=target.get("response_file_contents", []))
            actions[label] = record
        elif kind == "generated_file":
            for path in target["outputs"]:
                if path not in graph["generated_files"]:
                    raise ValueError("Missing literal GN metadata")
                input_file(path)
            record["outputs"] = target["outputs"]
            metadata[label] = record
        elif kind in ("static_library", "source_set", "group"):
            libraries[label] = capture_library(graph, target, record, input_file, label)
        else:
            raise ValueError("Untranslated typed Mojo target kind")
    for path in files:
        if not (chromium / path).is_file():
            raise ValueError("Missing original typed Mojo source: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return dict(roots=ROOTS, graph_sha256=graph_digest, names=names, libraries=libraries, actions=actions, metadata=metadata, producers=producers, files=sorted(files), headers=headers, external_files=shared_headers, external={label: external[label] for label in sorted(used)}, generated_files=generated, toolchain_deps=sorted(TOOLCHAIN))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    result = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, args.profiles)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

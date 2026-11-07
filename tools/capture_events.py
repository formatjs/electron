# SPDX-License-Identifier: MIT
"""Capture the full matching native UI events and tracing dependency closure."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_mojo import SCRIPTS as MOJO_SCRIPTS
from native_graph import BUILD, capture_library, load_profiles

ROOTS = ["//ui/events:events"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
SCRIPTS = MOJO_SCRIPTS | {"//build/write_buildflag_header.py", "//tools/protoc_wrapper/protoc_wrapper.py", "//tools/generate_library_loader/generate_library_loader.py"}
PINS = {"snappy": "32ded457c0b1fe78ceb8397632c416568d6714a0", "protobuf_javascript": "e6d763860001ba1a76a63adcff5efb12b1c96024"}


def capture(graph, digest, chromium, snappy, protobuf_javascript, perfetto, profiles):
    external, shared = load_profiles(profiles, [("base", "base"), ("embedder", "embedder"), ("ipcz", "ipcz"), ("libnode", "libnode"), ("perfetto", "perfetto_native"), ("protobuf", "protobuf"), ("v8_engine", "v8_engine"), ("v8_support", "v8_support"), ("network", "network"), ("mojo", "mojo"), ("fonts", "fonts"), ("codecs", "codecs"), ("skia", "skia"), ("gfx", "gfx"), ("display", "display")])
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}
    if any(rev not in (chromium / "DEPS").read_text() for rev in PINS.values()):
        raise ValueError("Events DEPS source pin changed")
    roots = {"third_party/snappy/src": snappy, "third_party/protobuf-javascript/src": protobuf_javascript, "third_party/perfetto": perfetto}

    def physical(path):
        for prefix, root in roots.items():
            if path.startswith(prefix + "/"):
                return root / path[len(prefix) + 1:]
        return chromium / path

    files, generated, headers, used_shared = set(), {}, {}, set()
    producers = {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "generated_file", "copy"):
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate events output")
                producers[output] = label

    tools = {output: label for label, target in targets.items() if target["type"] == "executable" and (label in seen or label in external) for output in target.get("outputs", [])[:1]}

    def input_file(path):
        if path in tools:
            return
        if path in shared:
            used_shared.add(path)
            return
        if path.startswith(BUILD):
            if path in graph["generated_files"]:
                generated[path] = graph["generated_files"][path]
            elif path not in producers:
                raise ValueError("Unowned events input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Invalid events source path")

    for directory in ["components/prefs", "components/system_cpu", "components/tracing", "components/variations", "components/version_info", "sandbox/policy", "services/metrics", "services/tracing", "third_party/snappy", "third_party/protobuf-javascript", "third_party/x11proto", "third_party/perfetto", "ui/events", "ui/gfx/x", "ui/latency", "url/mojom"]:
        inventory = set()
        for prefix, root in [(directory, physical(directory + "/"))] + [(prefix, root) for prefix, root in roots.items() if prefix.startswith(directory + "/")]:
            inventory.update(prefix + "/" + path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".hpp", ".inc", ".inl"))
        if not inventory:
            raise ValueError("Missing original events header inventory: " + directory)
        headers[directory] = sorted(inventory)
        for path in inventory:
            input_file("//" + path)
    actions, libraries, metadata, copies = {}, {}, {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 events profile")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind == "action":
            if target["script"] not in SCRIPTS:
                raise ValueError("Untranslated original events generator")
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [target["script"]])
            if target["script"] == "//tools/protoc_wrapper/protoc_wrapper.py":
                inputs.update("//" + path.relative_to(chromium).as_posix() for path in (chromium / "tools/protoc_wrapper").rglob("*.py") if "__pycache__" not in path.parts)
            args = [arg.replace("$SOURCE_ROOT/out/bazel-import/", "") for arg in target.get("args", [])]
            for arg in args:
                if arg.startswith("../../") and physical(arg[6:]).is_file():
                    inputs.add("//" + arg[6:])
                elif BUILD + arg in graph["generated_files"]:
                    inputs.add(BUILD + arg)
            if any("{{" in arg and arg != "{{response_file_name}}" for arg in args):
                raise ValueError("Untranslated events generator placeholder")
            for path in inputs:
                input_file(path)
            record.update(script=target["script"][2:], inputs=sorted(path for path in inputs if path not in tools), tools={path: tools[path] for path in sorted(inputs) if path in tools}, args=args, outputs=target["outputs"], response=target.get("response_file_contents", []))
            actions[label] = record
        elif kind == "copy":
            if len(target["sources"]) != len(target["outputs"]):
                raise ValueError("Untranslated original GN copy")
            for path in target["sources"]:
                input_file(path)
            record.update(sources=target["sources"], outputs=target["outputs"])
            copies[label] = record
        elif kind == "generated_file":
            for path in target["outputs"]:
                if path not in graph["generated_files"]:
                    raise ValueError("Missing captured literal events metadata")
                input_file(path)
            record["outputs"] = target["outputs"]
            metadata[label] = record
        elif kind in ("group", "static_library", "source_set", "executable"):
            libraries[label] = capture_library(graph, target, record, input_file, label)
        else:
            raise ValueError("Untranslated events target kind: " + kind)
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original events input: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return dict(roots=ROOTS, graph_sha256=digest, names=names, libraries=libraries, actions=actions, metadata=metadata, copies=copies, execution_tools=sorted(set(tools.values())), source_revisions=PINS, producers=producers, headers=headers, files=sorted(files), external_files={path: shared[path] for path in sorted(used_shared)}, external={label: external[label] for label in sorted(used)}, generated_files=generated, toolchain_deps=sorted(TOOLCHAIN))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "snappy-root", "protobuf-javascript-root", "perfetto-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, args.snappy_root, args.protobuf_javascript_root, args.perfetto_root, args.profiles)
    args.output.write_text(json.dumps(profile, indent=2) + "\n")


if __name__ == "__main__":
    main()

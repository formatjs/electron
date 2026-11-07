# SPDX-License-Identifier: MIT
"""Capture matching native display models and their original Mojo wire types."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_mojo import SCRIPTS as MOJO_SCRIPTS
from native_graph import BUILD, capture_library, load_profiles

ROOTS = ["//ui/display:display", "//ui/display/mojom:mojom"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
SCRIPTS = MOJO_SCRIPTS | {"//build/write_buildflag_header.py"}


def capture(graph, digest, chromium, profiles):
    external, shared = load_profiles(profiles, [("base", "base"), ("embedder", "embedder"), ("ipcz", "ipcz"), ("libnode", "libnode"), ("perfetto", "perfetto_native"), ("protobuf", "protobuf"), ("v8_engine", "v8_engine"), ("v8_support", "v8_support"), ("network", "network"), ("mojo", "mojo"), ("fonts", "fonts"), ("codecs", "codecs"), ("skia", "skia"), ("gfx", "gfx")])
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    prefixes = ("//ui/display", "//ui/gfx/", "//components/device_event_log:")
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        flags = targets[label]["type"] == "action" and targets[label].get("script") == "//build/write_buildflag_header.py"
        if not label.startswith(prefixes) and not flags:
            raise ValueError("Untranslated display dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}
    def physical(path):
        return chromium / path

    files, generated, headers, used_shared = set(), {}, {}, set()
    producers = {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "generated_file"):
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate display output")
                producers[output] = label

    def input_file(path):
        if path in shared:
            used_shared.add(path)
            return
        if path.startswith(BUILD):
            if path in graph["generated_files"]:
                generated[path] = graph["generated_files"][path]
            elif path not in producers:
                raise ValueError("Unowned display input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Invalid display source path")

    for directory in ["ui/display", "ui/gfx/mojom", "components/device_event_log"]:
        root = chromium / directory
        inventory = sorted(path.relative_to(chromium).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".hpp", ".inc", ".inl"))
        if not inventory:
            raise ValueError("Missing original display header inventory: " + directory)
        headers[directory] = inventory
        for path in inventory:
            input_file("//" + path)
    actions, libraries, metadata = {}, {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 display profile")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind == "action":
            if target["script"] not in SCRIPTS:
                raise ValueError("Untranslated original display generator")
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [target["script"]])
            args = [arg.replace("$SOURCE_ROOT/out/bazel-import/", "") for arg in target.get("args", [])]
            for arg in args:
                if arg.startswith("../../") and physical(arg[6:]).is_file():
                    inputs.add("//" + arg[6:])
                elif BUILD + arg in graph["generated_files"]:
                    inputs.add(BUILD + arg)
            if any("{{" in arg and arg != "{{response_file_name}}" for arg in args):
                raise ValueError("Untranslated display generator placeholder")
            for path in inputs:
                input_file(path)
            record.update(script=target["script"][2:], inputs=sorted(inputs), args=args, outputs=target["outputs"], response=target.get("response_file_contents", []))
            actions[label] = record
        elif kind == "generated_file":
            for path in target["outputs"]:
                if path not in graph["generated_files"]:
                    raise ValueError("Missing captured literal display metadata")
                input_file(path)
            record["outputs"] = target["outputs"]
            metadata[label] = record
        elif kind in ("group", "static_library", "source_set"):
            libraries[label] = capture_library(graph, target, record, input_file, label)
        else:
            raise ValueError("Untranslated display target kind: " + kind)
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original display input: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return dict(roots=ROOTS, graph_sha256=digest, names=names, libraries=libraries, actions=actions, metadata=metadata, producers=producers, headers=headers, files=sorted(files), external_files={path: shared[path] for path in sorted(used_shared)}, external={label: external[label] for label in sorted(used)}, generated_files=generated, toolchain_deps=sorted(TOOLCHAIN))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, args.profiles)
    args.output.write_text(json.dumps(profile, indent=2) + "\n")


if __name__ == "__main__":
    main()

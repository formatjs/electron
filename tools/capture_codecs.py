# SPDX-License-Identifier: MIT
"""Capture Chromium JPEG/WebP/Wuffs and matching native NASM without build wrappers."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from native_graph import BUILD, capture_library

ROOTS = ["//third_party:jpeg", "//third_party/libwebp:libwebp", "//third_party/wuffs:wuffs"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
PINS = {"jpeg": "e14cbfaa85529d47f9f55b0f104a579c1061f9ad", "webp": "b0e8039062eedbcb20ebb1bad62bfeaee2b94ec6", "wuffs": "e3f919ccfe3ef542cfc983a82146070258fb57f8", "nasm": "e2c93c34982b286b27ce8b56dd7159e0b90869a2"}


def capture(graph, digest, chromium, jpeg, webp, wuffs, nasm):
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    while pending:
        label = pending.pop()
        if label in seen or label in TOOLCHAIN:
            continue
        if label != "//third_party:jpeg" and not label.startswith(("//third_party/libjpeg_turbo:", "//third_party/libwebp:", "//third_party/wuffs:", "//third_party/nasm:")):
            raise ValueError("Untranslated codec dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    if any(revision not in (chromium / "DEPS").read_text() for revision in PINS.values()):
        raise ValueError("Codec/NASM DEPS pin changed")
    if (nasm / "version").read_text().strip() != "2.17rc0":
        raise ValueError("Expected original captured NASM version")
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}
    roots = {"third_party/libjpeg_turbo": jpeg, "third_party/libwebp/src": webp, "third_party/wuffs/src": wuffs, "third_party/nasm": nasm}

    def physical(path):
        for prefix, root in roots.items():
            if path.startswith(prefix + "/"):
                return root / path[len(prefix) + 1:]
        return chromium / path

    files, headers, textual = set(), {}, {}
    for directory in ("third_party/libjpeg_turbo", "third_party/libwebp", "third_party/wuffs", "third_party/nasm"):
        inventory = set()
        owner = roots.get(directory, chromium / directory)
        for prefix, root in [(directory, owner)] + [(prefix, root) for prefix, root in roots.items() if prefix.startswith(directory + "/")]:
            inventory.update(prefix + "/" + path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".hh", ".inc", ".inl", ".c"))
        if not inventory:
            raise ValueError("Missing codec/NASM header inventory")
        headers[directory] = sorted(path for path in inventory if not path.endswith(".c"))
        textual[directory] = sorted(path for path in inventory if path.endswith(".c"))
        files.update(inventory)
    actions, libraries, producers = {}, {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] == "action_foreach":
            for path in target["outputs"]:
                if not path.startswith(BUILD) or path in producers:
                    raise ValueError("Unexpected codec generated output")
                producers[path] = label

    def input_file(path):
        if path.startswith(BUILD):
            if path not in producers:
                raise ValueError("Unowned codec input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Invalid codec source path")

    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 codec toolchain")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind == "action_foreach":
            if target["script"] != "//build/gn_run_binary.py" or target["deps"] != ["//third_party/nasm:nasm"] or target["args"][0] != "nasm" or "--reproducible" not in target["args"]:
                raise ValueError("Unexpected original SIMD assembler action")
            if len(target["sources"]) != len(target["outputs"]):
                raise ValueError("Ambiguous SIMD assembly outputs")
            runs = []
            for source, output in zip(target["sources"], target["outputs"]):
                inputs = sorted(set(target["inputs"] + [source, target["script"]]))
                args = [arg.replace("{{source}}", "../../" + source[2:]).replace("{{source_name_part}}", Path(source).stem) for arg in target["args"]]
                if any("{{" in arg for arg in args):
                    raise ValueError("Untranslated SIMD action placeholder")
                for path in inputs:
                    input_file(path)
                runs.append(dict(inputs=inputs, outputs=[output], args=args, tools={"//out/bazel-import/nasm": ":" + names["//third_party/nasm:nasm"]}))
            record.update(script=target["script"][2:], response=target.get("response_file_contents", []), runs=runs, outputs=target["outputs"])
            actions[label] = record
        elif kind in ("group", "static_library", "source_set", "executable"):
            libraries[label] = capture_library(graph, target, record, input_file, label)
        else:
            raise ValueError("Untranslated codec target kind")
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original codec/NASM source: " + path)
    return dict(roots=ROOTS, graph_sha256=digest, source_revisions=PINS, names=names, libraries=libraries, actions=actions, producers=producers, files=sorted(files), headers=headers, textual_headers=textual, external={}, generated_files={}, toolchain_deps=sorted(TOOLCHAIN))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "jpeg-root", "webp-root", "wuffs-root", "nasm-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    result = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, args.jpeg_root, args.webp_root, args.wuffs_root, args.nasm_root)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

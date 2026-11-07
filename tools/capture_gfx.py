# SPDX-License-Identifier: MIT
"""Capture full matching ui/gfx, geometry/range wire types and native graphics helpers."""

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

from capture_mojo import SCRIPTS as MOJO_SCRIPTS
from native_graph import BUILD, capture_library, load_profiles

ROOTS = ["//ui/gfx:gfx", "//ui/gfx/codec:codec", "//ui/gfx:memory_buffer_sources", "//ui/base:ui_data_pack", "//ui/gfx/geometry/mojom:mojom", "//ui/gfx/range/mojom:mojom"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
PINS = {"libdrm": "ad78bb591d02162d3b90890aa4d0a238b2a37cde", "libsync": "f4f4387b6bf2387efbcfd1453af4892e8982faf6"}
SCRIPTS = MOJO_SCRIPTS | {"//build/write_buildflag_header.py", "//third_party/libdrm/src/gen_table_fourcc.py"}


def capture(graph, digest, chromium, libdrm, libsync, profiles):
    external, shared = load_profiles(profiles, [("base", "base"), ("embedder", "embedder"), ("ipcz", "ipcz"), ("libnode", "libnode"), ("perfetto", "perfetto_native"), ("protobuf", "protobuf"), ("v8_engine", "v8_engine"), ("v8_support", "v8_support"), ("network", "network"), ("mojo", "mojo"), ("fonts", "fonts"), ("codecs", "codecs"), ("skia", "skia")])
    if any(rev not in (chromium / "DEPS").read_text() for rev in PINS.values()):
        raise ValueError("Graphics DEPS source pin changed")
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    prefixes = ("//build/config/linux/libdrm:", "//ui/", "//cc/", "//gpu/", "//skia/public/mojom:", "//components/crash/core/common:", "//printing/buildflags:", "//third_party/crashpad/", "//third_party/libdrm:", "//third_party/libsync:", "//third_party/zlib/google:")
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        flags = targets[label]["type"] == "action" and targets[label].get("script") == "//build/write_buildflag_header.py"
        if not label.startswith(prefixes) and not flags:
            raise ValueError("Untranslated graphics dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}
    roots = {"third_party/libdrm/src": libdrm, "third_party/libsync/src": libsync}

    def physical(path):
        for prefix, root in roots.items():
            if path.startswith(prefix + "/"):
                return root / path[len(prefix) + 1:]
        return chromium / path

    files, generated, headers, used_shared = set(), {}, {}, set()
    producers = {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "generated_file"):
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate graphics output")
                producers[output] = label

    def input_file(path):
        if path in shared:
            used_shared.add(path)
            return
        if path.startswith(BUILD):
            if path in graph["generated_files"]:
                generated[path] = graph["generated_files"][path]
            elif path not in producers:
                raise ValueError("Unowned graphics input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Invalid graphics source path")

    for directory in ["cc/base", "cc/debug", "cc/paint", "components/crash/core/common", "gpu/command_buffer/common", "skia/public/mojom", "third_party/crashpad/crashpad", "third_party/libdrm", "third_party/libsync", "third_party/zlib/google", "ui/base", "ui/display/types", "ui/gfx", "ui/linux"]:
        inventory = set()
        for prefix, root in [(directory, chromium / directory)] + [(prefix, root) for prefix, root in roots.items() if prefix.startswith(directory + "/")]:
            inventory.update(prefix + "/" + path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".hpp", ".inc", ".inl"))
        if not inventory:
            raise ValueError("Missing original graphics header inventory: " + directory)
        headers[directory] = sorted(inventory)
        for path in inventory:
            input_file("//" + path)
    headers["cc"] = sorted(path.relative_to(chromium).as_posix() for path in (chromium / "cc").glob("*.h"))
    for path in headers["cc"]:
        input_file("//" + path)
    actions, libraries, metadata = {}, {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 graphics profile")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind == "action":
            if target["script"] not in SCRIPTS:
                raise ValueError("Untranslated original graphics generator")
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [target["script"]])
            args = [arg.replace("$SOURCE_ROOT/out/bazel-import/", "") for arg in target.get("args", [])]
            for arg in args:
                if arg.startswith("../../") and physical(arg[6:]).is_file():
                    inputs.add("//" + arg[6:])
                elif BUILD + arg in graph["generated_files"]:
                    inputs.add(BUILD + arg)
            if any("{{" in arg and arg != "{{response_file_name}}" for arg in args):
                raise ValueError("Untranslated graphics generator placeholder")
            for path in inputs:
                input_file(path)
            record.update(script=target["script"][2:], inputs=sorted(inputs), args=args, outputs=target["outputs"], response=target.get("response_file_contents", []))
            actions[label] = record
        elif kind == "generated_file":
            for path in target["outputs"]:
                if path not in graph["generated_files"]:
                    raise ValueError("Missing captured literal graphics metadata")
                input_file(path)
            record["outputs"] = target["outputs"]
            metadata[label] = record
        elif kind in ("group", "static_library", "source_set"):
            libraries[label] = capture_library(graph, target, record, input_file, label)
        else:
            raise ValueError("Untranslated graphics target kind: " + kind)
    textual_headers = set()
    for library in libraries.values():
        for path in library["asm_srcs"]:
            for include in re.findall(r'^\s*#\s*include\s*["<]([^">]+\.S)[">]', physical(path[2:]).read_text(), re.M):
                candidate = "third_party/crashpad/crashpad/" + include
                if not physical(candidate).is_file():
                    raise ValueError("Missing original assembly include: " + include)
                textual_headers.add(candidate)
                input_file("//" + candidate)
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original graphics input: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return dict(roots=ROOTS, graph_sha256=digest, source_revisions=PINS, names=names, libraries=libraries, actions=actions, metadata=metadata, producers=producers, headers=headers, textual_headers=sorted(textual_headers), files=sorted(files), external_files={path: shared[path] for path in sorted(used_shared)}, external={label: external[label] for label in sorted(used)}, generated_files=generated, toolchain_deps=sorted(TOOLCHAIN))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "libdrm-root", "libsync-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, args.libdrm_root, args.libsync_root, args.profiles)
    args.output.write_text(json.dumps(profile, indent=2) + "\n")


if __name__ == "__main__":
    main()

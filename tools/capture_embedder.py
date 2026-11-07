# SPDX-License-Identifier: MIT
"""Capture matching Gin, Base i18n and CED for Electron's Chromium embedder."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

BUILD = "//out/bazel-import/"
ROOTS = ["//gin:gin", "//base:i18n"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers")}


def capture(graph, chromium, ced, base):
    if "ba412eaaacd3186085babcd901679a48863c7dd5" not in (chromium / "DEPS").read_text():
        raise ValueError("CED DEPS pin changed")
    external = {label: "@electron_base_sources//:" + name for label, name in base["names"].items()}
    external.update({"//third_party/icu:icu": "@electron_icu_sources//:icu", "//third_party/abseil-cpp:absl": "@electron_protobuf_sources//:abseil", "//v8:v8": "@electron_v8_engine_sources//:v8"})
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        if label not in ["//gin:gin", "//base:i18n", "//base:i18n_transliterator", "//third_party/ced:ced", "//tools/v8_context_snapshot:buildflags"]:
            raise ValueError("Untranslated embedder dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}

    def value(target, key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    def physical(path):
        return ced / path.removeprefix("third_party/ced/src/") if path.startswith("third_party/ced/src/") else chromium / path

    files, headers, actions, libraries, producers = set(), {}, {}, {}, {}
    for family, directory, prefix in [("gin", chromium / "gin", "gin/"), ("ced", ced, "third_party/ced/src/")]:
        headers[family] = sorted(prefix + path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file() and path.suffix in (".h", ".inc", ".inl", ".hpp"))
        if not headers[family]:
            raise ValueError("Missing embedder header inventory")
        files.update(headers[family])
    headers["i18n"] = sorted(path[2:] for path in targets["//base:i18n"]["sources"] if path.endswith(".h"))
    files.add("third_party/ced/src/LICENSE")
    for label in sorted(seen):
        target = targets[label]
        if target["type"] == "action":
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate embedder output")
                producers[output] = label
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 embedder profile")
        record = {"name": names[label], "kind": target["type"], "gn_deps": target.get("deps", [])}
        if target["type"] == "action":
            if target["script"] != "//build/write_buildflag_header.py" or target.get("inputs") or target.get("sources"):
                raise ValueError("Unknown embedder generator")
            files.add(target["script"][2:])
            record.update(script=target["script"][2:], args=target["args"], response=target["response_file_contents"], outputs=target["outputs"])
            actions[label] = record
        elif target["type"] == "static_library":
            sources = target.get("sources", [])
            if any(Path(path).suffix not in (".h", ".cc", ".cpp") for path in sources):
                raise ValueError("Unexpected embedder language")
            files.update(path[2:] for path in sources)
            flags, omitted = [], []
            for flag in value(target, "cflags") + value(target, "cflags_cc"):
                if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                    omitted.append(flag)
                else:
                    flags.append(flag)
            includes = []
            for path in value(target, "include_dirs"):
                if path == "//buildtools/third_party/libc++/":
                    continue
                if path.startswith(BUILD):
                    includes.append(path.removeprefix(BUILD).rstrip("/") or ".")
                elif path.startswith("//"):
                    includes.append(path[2:].rstrip("/") or ".")
                else:
                    raise ValueError("Unexpected embedder include root")
            libs = value(target, "libs")
            if set(libs) - {"dl", "rt", "glib-2.0", "gmodule-2.0", "gobject-2.0", "gthread-2.0", "$LLVM_ROOT/lib/clang/23/lib/x86_64-unknown-linux-gnu/libclang_rt.builtins.a"}:
                raise ValueError("Untranslated embedder link library")
            record.update(srcs=[path for path in sources if path.endswith((".cc", ".cpp"))], copts=flags, defines=[item.replace('"', '\\"') for item in value(target, "defines")], includes=includes, libs=libs, gn_include_dirs=value(target, "include_dirs"), gn_ldflags=value(target, "ldflags"), omitted_toolchain_and_diagnostic_flags=omitted)
            libraries[label] = record
        else:
            raise ValueError("Unexpected embedder target kind")
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original embedder input: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return {"roots": ROOTS, "names": names, "libraries": libraries, "actions": actions, "producers": producers, "external": {label: external[label] for label in sorted(used)}, "files": sorted(files), "headers": headers, "toolchain_deps": sorted(TOOLCHAIN)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["graph", "chromium-root", "ced-root", "base-profile", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    result = capture(json.loads(gzip.decompress(content)), args.chromium_root, args.ced_root, json.loads(args.base_profile.read_text()))
    result["graph_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

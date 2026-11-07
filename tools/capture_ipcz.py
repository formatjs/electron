# SPDX-License-Identifier: MIT
"""Capture Electron's Chromium-configured IPCz dependency without standalone shims."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

ROOT = "//third_party/ipcz/src:ipcz_chromium"
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers")}
DRIVER_SOURCES = ["third_party/ipcz/src/reference_drivers/" + name + ".cc" for name in ("object", "random", "single_process_reference_driver_base", "sync_reference_driver")]


def capture(graph, chromium, base):
    external = {label: "@electron_base_sources//:" + name for label, name in base["names"].items()}
    external["//third_party/abseil-cpp:absl"] = "@electron_protobuf_sources//:abseil"
    targets, seen, pending = graph["targets"], set(), [ROOT]
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        if not label.startswith("//third_party/ipcz/src:"):
            raise ValueError("Untranslated IPCz dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}

    def value(target, key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    directory = chromium / "third_party/ipcz"
    headers = sorted(path.relative_to(chromium).as_posix() for path in directory.rglob("*") if path.is_file() and path.suffix in (".h", ".inc", ".inl", ".hpp"))
    if not headers:
        raise ValueError("Missing original IPCz header inventory")
    files, libraries = set(headers + DRIVER_SOURCES + ["third_party/ipcz/LICENSE"]), {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] != "source_set" or target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 IPCz source set")
        sources = target.get("sources", [])
        if any(not path.startswith("//third_party/ipcz/") or Path(path).suffix not in (".h", ".cc") for path in sources):
            raise ValueError("Unexpected IPCz source")
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
            if path.startswith("//out/bazel-import/"):
                includes.append(path.removeprefix("//out/bazel-import/").rstrip("/") or ".")
            elif path.startswith("//"):
                includes.append(path[2:].rstrip("/") or ".")
            else:
                raise ValueError("Unexpected IPCz include root")
        libs = value(target, "libs")
        if set(libs) - {"dl", "rt", "glib-2.0", "gmodule-2.0", "gobject-2.0", "gthread-2.0", "$LLVM_ROOT/lib/clang/23/lib/x86_64-unknown-linux-gnu/libclang_rt.builtins.a"}:
            raise ValueError("Untranslated IPCz link library")
        defines = value(target, "defines")
        if "IPCZ_STANDALONE" in defines:
            raise ValueError("Expected original Chromium IPCz configuration")
        libraries[label] = dict(name=names[label], kind=target["type"], gn_deps=target.get("deps", []), srcs=[path for path in sources if path.endswith(".cc")], copts=flags, defines=[item.replace('"', '\\"') for item in defines], includes=includes, libs=libs, gn_include_dirs=value(target, "include_dirs"), gn_ldflags=value(target, "ldflags"), omitted_toolchain_and_diagnostic_flags=omitted)
    for path in files:
        if not (chromium / path).is_file():
            raise ValueError("Missing original IPCz input: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return dict(roots=[ROOT], names=names, libraries=libraries, external={label: external[label] for label in sorted(used)}, files=sorted(files), headers=headers, toolchain_deps=sorted(TOOLCHAIN), test_driver_sources=DRIVER_SOURCES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "base-profile", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    result = capture(json.loads(gzip.decompress(content)), args.chromium_root, json.loads(args.base_profile.read_text()))
    result["graph_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

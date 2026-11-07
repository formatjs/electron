# SPDX-License-Identifier: MIT
"""Capture Electron's complete matching PartitionAlloc native profile."""

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path


def capture(graph, source):
    root = "//base/allocator/partition_allocator/"
    prefix = root + "src/partition_alloc:"
    groups = {
        root[:-1] + ":partition_alloc": [prefix + "partition_alloc"],
        prefix + "partition_alloc": [prefix + name for name in ("allocator_base", "allocator_core", "allocator_shim", "buildflags")],
    }
    for label, dependencies in groups.items():
        target = graph["targets"][label]
        if target["type"] != "group" or target["deps"] != dependencies:
            raise ValueError("Untranslated PartitionAlloc aggregate dependency")
    toolchain = {"//buildtools/third_party/libc++:all_modules", "//buildtools/third_party/libc++:custom_headers", "//buildtools/third_party/libc++:libcxx_headers"}
    edges = {
        "allocator_base": {"build_config", "buildflags"},
        "allocator_core": {"allocator_base", "build_config", "buildflags"},
        "allocator_shim": {"allocator_base", "allocator_core", "buildflags"},
        "raw_ptr": {"build_config", "buildflags", "partition_alloc"},
        "build_config": {"buildflag_macro", "buildflags"},
        "buildflag_macro": set(),
    }
    libraries, headers = {}, []
    for name, dependencies in edges.items():
        target = graph["targets"][prefix + name]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected PartitionAlloc Linux AMD64 toolchain")
        kind = "static_library" if name.startswith("allocator_") or name == "raw_ptr" else "source_set"
        if target["type"] != kind or set(target["deps"]) != toolchain | {prefix + dep for dep in dependencies}:
            raise ValueError("Untranslated PartitionAlloc dependency")

        def value(key):
            item = target.get(key, [])
            return graph["pool"][item["pool"]] if isinstance(item, dict) else item

        if any(not p.startswith(root) or not p.endswith((".cc", ".h", ".inc")) for p in target["sources"]):
            raise ValueError("Unexpected PartitionAlloc source inventory")
        paths = [p.removeprefix(root) for p in target["sources"]]
        flags, omitted = [], []
        for flag in value("cflags") + value("cflags_cc"):
            if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                omitted.append(flag)
            else:
                flags.append(flag)
        if kind == "source_set":
            if any(p.endswith(".cc") for p in paths):
                raise ValueError("Untranslated PartitionAlloc header implementation")
            headers += paths
        else:
            if "-fno-exceptions" not in flags or "-fno-rtti" not in flags:
                raise ValueError("Unexpected PartitionAlloc language profile")
            libraries[name] = {
                "srcs": [p for p in paths if p.endswith(".cc")],
                "hdrs": [p for p in paths if p.endswith((".h", ".inc"))],
                "copts": flags,
                "defines": [d.replace('"', '\\"') for d in value("defines")],
                "gn_defines": value("defines"),
                "gn_deps": target["deps"],
                "gn_include_dirs": value("include_dirs"),
                "gn_ldflags": value("ldflags"),
                "omitted_toolchain_and_diagnostic_flags": omitted,
            }
    libraries["raw_ptr"]["hdrs"].append("src/partition_alloc/pointers/instance_tracer.h")
    source_headers = source / "base/allocator/partition_allocator/src"
    public_headers = set()
    pending = [path.relative_to(source_headers).as_posix() for path in (source_headers / "partition_alloc/pointers").glob("*.h")]
    if not pending:
        raise ValueError("Missing original raw pointer header family")
    while pending:
        relative = pending.pop()
        if relative in public_headers or relative == "partition_alloc/buildflags.h":
            continue
        path = source_headers / relative
        if not path.is_file() or not path.resolve().is_relative_to(source_headers.resolve()):
            raise ValueError("Missing original raw pointer header: " + relative)
        public_headers.add(relative)
        pending.extend(re.findall(r'^\s*#\s*include\s*["<](partition_alloc/[^">]+)[">]', path.read_text(), re.M))
    libraries["raw_ptr"]["public_headers"] = sorted("src/" + path for path in public_headers)
    action = graph["targets"][prefix + "buildflags"]
    output = "base/allocator/partition_allocator/src/partition_alloc/buildflags.h"
    if action["type"] != "action" or action["script"] != root + "src/partition_alloc/write_buildflag_header.py" or action["deps"] != [prefix + "buildflag_macro"] or action.get("inputs") or action.get("sources"):
        raise ValueError("Unexpected PartitionAlloc buildflag action")
    if action["args"] != ["--output", output, "--rulename", prefix + "buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"] or action["outputs"] != ["//out/bazel-import/gen/" + output]:
        raise ValueError("Unexpected PartitionAlloc buildflag arguments")
    response = action["response_file_contents"]
    if response[0] != "--flags" or not {"USE_PARTITION_ALLOC=true", "USE_PARTITION_ALLOC_AS_MALLOC=true", "USE_ALLOCATOR_SHIM=true"}.issubset(response):
        raise ValueError("Expected captured PartitionAlloc allocator/shim configuration")
    # Direct includes absent from GN inventories, including inactive OS branches.
    headers += [
        "src/partition_alloc/page_allocator_internals_fuchsia.h",
        "src/partition_alloc/page_allocator_internals_win.h",
        "src/partition_alloc/partition_alloc_base/apple/foundation_util.h",
        "src/partition_alloc/partition_alloc_base/apple/scoped_cftyperef.h",
        "src/partition_alloc/partition_alloc_base/files/file_path.h",
        "src/partition_alloc/partition_alloc_base/ios/ios_util.h",
        "src/partition_alloc/partition_alloc_base/mac/mac_util.h",
        "src/partition_alloc/partition_alloc_base/native_library.h",
        "src/partition_alloc/shim/allocator_shim_default_dispatch_to_partition_alloc_internal.h",
    ]
    return libraries, sorted(headers), {"output": output, "rule": prefix + "buildflags", "response": response}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    libraries, headers, flags = capture(json.loads(gzip.decompress(content)), args.source_root)
    args.output.write_text('"""PartitionAlloc from Electron 39 Linux AMD64 GN capture."""\n\nPARTITION_ALLOC_PROFILE_SHA256 = ' + repr(hashlib.sha256(content).hexdigest()) + '\n\nPARTITION_ALLOC_LIBRARIES = ' + json.dumps(libraries, indent=4) + '\n\nPARTITION_ALLOC_HEADERS = ' + json.dumps(headers, indent=4) + '\n\nPARTITION_ALLOC_BUILDFLAGS = ' + json.dumps(flags, indent=4) + '\n')


if __name__ == "__main__":
    main()

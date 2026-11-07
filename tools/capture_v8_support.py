# SPDX-License-Identifier: MIT
"""Capture V8's exact non-engine number, SIMD and compression dependencies."""

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path


ROOTS = {
    "dragonbox": "third_party/dragonbox/src",
    "fast_float": "third_party/fast_float/src",
    "highway": "third_party/highway/src",
    "simdutf": "third_party/simdutf",
    "zlib": "third_party/zlib",
}
TARGETS = {
    "//third_party/dragonbox:dragonbox": "dragonbox",
    "//third_party/fast_float:fast_float": "fast_float",
    "//third_party/highway:libhwy": "highway",
    "//third_party/simdutf:header": "simdutf_headers",
    "//third_party/simdutf:simdutf": "simdutf",
    "//third_party/zlib:zlib": "zlib",
    "//third_party/zlib:zlib_adler32_simd": "zlib_adler32_simd",
    "//third_party/zlib:zlib_common_headers": "zlib_headers",
    "//third_party/zlib:zlib_crc32_simd": "zlib_crc32_simd",
    "//third_party/zlib:zlib_data_chunk_simd": "zlib_data_chunk_simd",
    "//third_party/zlib:zlib_slide_hash_simd": "zlib_slide_hash_simd",
    "//third_party/zlib/google:compression_utils_portable": "compression_utils_portable",
}
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers")}
REVISIONS = {
    "dragonbox": "6c7c925b571d54486b9ffae8d9d18a822801cbda",
    "fast_float": "cb1d42aaa1e14b09e1452cfdef373d051b8c02a4",
    "highway": "84379d1c73de9681b54fbe1c035a23c7bd5d272d",
}


def capture(graph, roots):
    deps = (roots["chromium"] / "DEPS").read_text()
    for name, revision in REVISIONS.items():
        entry = re.search(r"'src/" + re.escape(ROOTS[name]) + r"'\s*:\s*\n([^\n]+)", deps)
        if not entry:
            raise ValueError("Missing V8 support DEPS entry: " + name)
        pin = entry[1]
        if name == "highway":
            variable = re.search(r"'highway_revision':\s*'([0-9a-f]{40})'", deps)
            if "Var('highway_revision')" not in pin or not variable or variable[1] != revision:
                raise ValueError("Highway DEPS pin changed")
        elif revision not in pin:
            raise ValueError("V8 support DEPS pin changed: " + name)

    def value(target, key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    libraries, headers, files = {}, {}, set()
    for name, prefix in ROOTS.items():
        directory = roots[name]
        headers[name] = sorted(prefix + "/" + path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file() and path.suffix in (".h", ".inc", ".inl"))
        if not headers[name]:
            raise ValueError("Missing pinned dependency headers: " + name)
        files.update(headers[name])
        files.update(prefix + "/" + path.name for path in directory.iterdir() if path.is_file() and path.name.startswith(("LICENSE", "COPYING", "NOTICE")))
    for label, name in TARGETS.items():
        target = graph["targets"][label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64" or target["type"] not in ("source_set", "static_library"):
            raise ValueError("Unexpected V8 support target profile")
        if set(target["deps"]) - TOOLCHAIN - TARGETS.keys():
            raise ValueError("Untranslated V8 support dependency")
        family = label.split("/")[3].split(":")[0]
        sources = target.get("sources", [])
        public = target.get("public", [])
        if isinstance(public, list):
            sources = sources + public
        if any(not path.startswith("//third_party/" + family + "/") or not path.endswith((".cc", ".cpp", ".c", ".h", ".inc", ".inl")) for path in sources):
            raise ValueError("Unexpected V8 support source path")
        logical = [path.removeprefix("//") for path in sources]
        files.update(logical)
        source_files = [path for path in logical if path.endswith((".cc", ".cpp", ".c"))]
        if source_files and any(path.endswith(".c") != source_files[0].endswith(".c") for path in source_files):
            raise ValueError("Mixed C/C++ support target needs separate native actions")
        language = "cflags_c" if source_files and source_files[0].endswith(".c") else "cflags_cc"
        flags, omitted = [], []
        for flag in value(target, "cflags") + value(target, language):
            if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                omitted.append(flag)
            else:
                flags.append(flag)
        includes = []
        for path in value(target, "include_dirs"):
            if path in ("//", "//out/bazel-import/gen/", "//buildtools/third_party/libc++/"):
                continue
            if not path.startswith("//third_party/" + family + "/"):
                raise ValueError("Untranslated V8 support include directory")
            includes.append(path.removeprefix("//").rstrip("/"))
        libraries[name] = {
            "kind": target["type"],
            "srcs": source_files,
            "family": family,
            "copts": flags,
            "defines": [item.replace('"', '\\"') for item in value(target, "defines")],
            "includes": includes,
            "deps": [TARGETS[dep] for dep in target["deps"] if dep not in TOOLCHAIN],
            "gn_label": label,
            "gn_deps": target["deps"],
            "gn_include_dirs": value(target, "include_dirs"),
            "gn_ldflags": value(target, "ldflags"),
            "omitted_toolchain_and_diagnostic_flags": omitted,
        }
    files.update(["build/build_config.h", "build/buildflag.h", "LICENSE"])
    for path in files:
        owner = next((key for key, prefix in ROOTS.items() if path.startswith(prefix + "/")), None)
        physical = roots[owner] / path.removeprefix(ROOTS[owner] + "/") if owner else roots["chromium"] / path
        if not physical.is_file():
            raise ValueError("Missing pinned V8 support input: " + path)
    return {"libraries": libraries, "headers": headers, "files": sorted(files), "roots": ROOTS, "revisions": REVISIONS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--chromium-root", type=Path, required=True)
    for name in ("dragonbox", "fast_float", "highway"):
        parser.add_argument("--" + name.replace("_", "-") + "-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roots = {"chromium": args.chromium_root, "dragonbox": args.dragonbox_root, "fast_float": args.fast_float_root, "highway": args.highway_root}
    roots.update({name: args.chromium_root / ROOTS[name] for name in ("simdutf", "zlib")})
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), roots)
    profile["graph_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.write_text(json.dumps(profile, indent=2) + "\n")


if __name__ == "__main__":
    main()

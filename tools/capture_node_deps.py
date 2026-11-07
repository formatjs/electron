# SPDX-License-Identifier: MIT
"""Capture Linux Node dependency compilation inputs from the verified GN graph."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

LIBRARIES = ("ada", "cares", "histogram", "llhttp", "nghttp2", "simdjson", "sqlite", "uvwasi")
PREFIX = "//third_party/electron_node/"
TOOLCHAIN_DEPS = {
    "//buildtools/third_party/libc++:all_modules",
    "//buildtools/third_party/libc++:custom_headers",
    "//buildtools/third_party/libc++:libcxx_headers",
}


def capture(graph):
    def value(target, key):
        result = target.get(key, [])
        return graph["pool"][result["pool"]] if isinstance(result, dict) else result

    libraries = {}
    for name in LIBRARIES:
        label = PREFIX + "deps/" + name + ":" + name
        target = graph["targets"][label]
        sources = [path for path in target["sources"] if path.endswith((".c", ".cc", ".cpp"))]
        if not sources or any(not path.startswith(PREFIX + "deps/" + name + "/") for path in sources):
            raise ValueError("Unexpected dependency source inventory: " + label)
        languages = {"c" if path.endswith(".c") else "cc" for path in sources}
        if len(languages) != 1:
            raise ValueError("Mixed-language dependency needs separate compilation rules")
        deps = set(target.get("deps", [])) - TOOLCHAIN_DEPS
        expected = {PREFIX + "deps/uv:uv"} if name == "uvwasi" else set()
        if deps != expected:
            raise ValueError("Untranslated dependency edge: " + label)
        includes, omitted_includes = [], []
        for path in value(target, "include_dirs"):
            if path.startswith(PREFIX):
                includes.append(path.removeprefix(PREFIX).rstrip("/"))
            elif path in ("//", "//out/bazel-import/gen/", "//buildtools/third_party/libc++/"):
                omitted_includes.append(path)
            else:
                raise ValueError("Untranslated include directory: " + path)
        flags, omitted_flags = [], []
        for flag in value(target, "cflags") + value(target, "cflags_" + next(iter(languages))):
            if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                omitted_flags.append(flag)
            else:
                flags.append(flag)
        libraries[name] = {
            "gn_label": label,
            "srcs": [path.removeprefix(PREFIX) for path in sources],
            "includes": includes,
            "defines": value(target, "defines"),
            "copts": flags,
            "deps": [":libuv"] if deps else [],
            "omitted_toolchain_and_diagnostic_flags": omitted_flags,
            "omitted_global_and_toolchain_includes": omitted_includes,
        }
    return libraries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    libraries = capture(json.loads(gzip.decompress(content)))
    args.output.write_text('"""Exact Linux AMD64 Node dependencies; source toolchain paths use hermetic LLVM."""\n\nGRAPH_SHA256 = ' + repr(hashlib.sha256(content).hexdigest()) + '\n\nNODE_DEPENDENCIES = ' + json.dumps(libraries, indent=4) + '\n')


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Capture Electron's matching Chromium ICU libraries and file-backed data."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def capture(graph):
    prefix = "//third_party/icu/"
    toolchain = {"//buildtools/third_party/libc++:custom_headers", "//buildtools/third_party/libc++:libcxx_headers"}
    expected = {
        "icuuc_private": toolchain | {"//third_party/icu:icudata", "//third_party/icu:icuuc_public"},
        "icui18n": toolchain | {"//third_party/icu:icuuc_private"},
    }
    libraries = {}
    public_defines = ["U_USING_ICU_NAMESPACE=0", "U_ENABLE_DYLOAD=0", "USE_CHROMIUM_ICU=1", "U_ENABLE_TRACING=1", "U_ENABLE_RESOURCE_TRACING=0", "U_STATIC_IMPLEMENTATION", "ICU_UTIL_DATA_IMPL=ICU_UTIL_DATA_FILE"]
    for name, dependencies in expected.items():
        target = graph["targets"]["//third_party/icu:" + name]
        if target["type"] != "static_library" or set(target["deps"]) != dependencies:
            raise ValueError("Untranslated ICU library dependency")

        def value(key):
            item = target.get(key, [])
            return graph["pool"][item["pool"]] if isinstance(item, dict) else item

        paths = target["sources"]
        public_headers = target.get("public", [])
        public_headers = public_headers if isinstance(public_headers, list) else []
        if any(not p.startswith(prefix) or not p.endswith((".cpp", ".h")) for p in paths + public_headers):
            raise ValueError("Unexpected ICU source inventory")
        flags, omitted = [], []
        for flag in value("cflags") + value("cflags_cc"):
            if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                omitted.append(flag)
            else:
                flags.append(flag)
        definitions = value("defines")
        if not set(public_defines).issubset(definitions) or "-frtti" not in flags or "-fno-exceptions" not in flags:
            raise ValueError("Expected captured file-backed ICU profile")
        libraries[name] = {
            "srcs": [p.removeprefix(prefix) for p in paths if p.endswith(".cpp")],
            "hdrs": sorted({p.removeprefix(prefix) for p in paths + public_headers if p.endswith(".h")}),
            "copts": flags,
            "defines": [d.replace('"', '\\"') for d in definitions],
            "gn_defines": definitions,
            "gn_deps": target["deps"],
            "gn_inputs": target.get("inputs", []),
            "gn_public": target.get("public", "*"),
            "gn_include_dirs": value("include_dirs"),
            "gn_ldflags": value("ldflags"),
            "omitted_toolchain_and_diagnostic_flags": omitted,
        }
    public = graph["targets"]["//third_party/icu:icuuc_public"]
    if public["type"] != "source_set" or set(public["deps"]) != toolchain | {"//buildtools/third_party/libc++:all_modules"} or any(not p.startswith(prefix) or not p.endswith(".h") for p in public["sources"]):
        raise ValueError("Unexpected ICU public header profile")
    data = graph["targets"]["//third_party/icu:copy_icudata"]
    if data["type"] != "copy" or data["deps"] or data["sources"] != [prefix + "common/icudtl.dat"] or data["outputs"] != ["//out/bazel-import/icudtl.dat"]:
        raise ValueError("Unexpected ICU data producer")
    return libraries, {
        "hdrs": [p.removeprefix(prefix) for p in public["sources"]],
        "defines": public_defines,
        "data": "common/icudtl.dat",
        # Direct include omitted from the GN sources/public lists.
        "supplemental_headers": ["source/stubdata/stubdata.h"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    libraries, public = capture(json.loads(gzip.decompress(content)))
    args.output.write_text('"""Matching Chromium ICU from Electron 39 Linux AMD64 GN capture."""\n\nICU_PROFILE_SHA256 = ' + repr(hashlib.sha256(content).hexdigest()) + '\n\nICU_LIBRARIES = ' + json.dumps(libraries, indent=4) + '\n\nICU_PUBLIC = ' + json.dumps(public, indent=4) + '\n')


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Capture Electron's complete bytecode handler generator profile."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def capture(graph):
    target = graph["targets"]["//v8:bytecode_builtins_list_generator"]
    expected = {
        "//build/config:executable_deps", "//build/win:default_exe_manifest",
        "//buildtools/third_party/libc++:all_modules",
        "//buildtools/third_party/libc++:custom_headers",
        "//buildtools/third_party/libc++:libcxx_headers",
        "//v8:v8_dump_build_config", "//v8:v8_libbase",
        "//v8:v8_shared_internal_headers",
    }
    if target["type"] != "executable" or set(target["deps"]) != expected:
        raise ValueError("Untranslated bytecode generator dependency")

    def value(key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    sources = [p for p in target["sources"] if p.endswith(".cc")]
    if set(sources) != {
        "//v8/src/builtins/generate-bytecodes-builtins-list.cc",
        "//v8/src/interpreter/bytecode-operands.cc",
        "//v8/src/interpreter/bytecodes.cc",
    }:
        raise ValueError("Unexpected bytecode generator source inventory")
    definitions = value("defines")
    if not {"V8_ENABLE_SANDBOX", "V8_TEMPORAL_SUPPORT", "V8_USE_PERFETTO", "V8_INTL_SUPPORT", "V8_TARGET_ARCH_X64", "V8_TARGET_OS_LINUX"}.issubset(definitions):
        raise ValueError("Expected Electron Linux AMD64 bytecode profile")
    flags, omitted = [], []
    for flag in value("cflags") + value("cflags_cc"):
        if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
            omitted.append(flag)
        else:
            flags.append(flag)
    if "-fno-exceptions" not in flags or "-fno-rtti" not in flags:
        raise ValueError("Unexpected bytecode generator language profile")
    action = graph["targets"]["//v8:generate_bytecode_builtins_list"]
    if action["type"] != "action" or action["script"] != "//v8/tools/run.py" or action["deps"] != ["//v8:bytecode_builtins_list_generator"] or action.get("inputs") or action.get("sources"):
        raise ValueError("Unexpected bytecode generation action")
    output = "builtins-generated/bytecodes-builtins-list.h"
    if action["args"] != ["./bytecode_builtins_list_generator", "gen/v8/" + output] or action["outputs"] != ["//out/bazel-import/gen/v8/" + output]:
        raise ValueError("Unexpected bytecode generation outputs")
    return {
        "srcs": [p.removeprefix("//v8/") for p in sources],
        "copts": flags,
        "defines": [d.replace('"', '\\"') for d in definitions],
        "gn_defines": definitions,
        "gn_deps": target["deps"],
        "gn_inputs": target.get("inputs", []),
        "gn_include_dirs": value("include_dirs"),
        "gn_ldflags": value("ldflags"),
        "omitted_toolchain_and_diagnostic_flags": omitted,
        "output": output,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)))
    args.output.write_text('"""Bytecode generator from Electron 39 Linux AMD64 GN capture."""\n\nBYTECODE_PROFILE_SHA256 = ' + repr(hashlib.sha256(content).hexdigest()) + '\n\nBYTECODE_GENERATOR = ' + json.dumps(profile, indent=4) + '\n')


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Capture complete Electron V8 generators with one declared output."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

GENERATORS = {
    "bytecodes": {
        "tool": "bytecode_builtins_list_generator",
        "action": "generate_bytecode_builtins_list",
        "sources": ["src/builtins/generate-bytecodes-builtins-list.cc", "src/interpreter/bytecode-operands.cc", "src/interpreter/bytecodes.cc"],
        "output": "builtins-generated/bytecodes-builtins-list.h",
        "deps": [],
        "variable": "BYTECODE",
        "title": "Bytecode generator",
    },
    "regexp": {
        "tool": "gen-regexp-special-case",
        "action": "run_gen-regexp-special-case",
        "sources": ["src/regexp/gen-regexp-special-case.cc"],
        "output": "src/regexp/special-case.cc",
        "deps": ["//third_party/icu:icu"],
        "variable": "REGEXP",
        "title": "Regexp special-case generator",
    },
}


def capture(graph, name):
    spec = GENERATORS[name]
    target = graph["targets"]["//v8:" + spec["tool"]]
    expected = {
        "//build/config:executable_deps", "//build/win:default_exe_manifest",
        "//buildtools/third_party/libc++:all_modules",
        "//buildtools/third_party/libc++:custom_headers",
        "//buildtools/third_party/libc++:libcxx_headers",
        "//v8:v8_dump_build_config", "//v8:v8_libbase",
        "//v8:v8_shared_internal_headers",
    } | set(spec["deps"])
    if target["type"] != "executable" or set(target["deps"]) != expected:
        raise ValueError("Untranslated V8 generator dependency")

    def value(key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    sources = [p.removeprefix("//v8/") for p in target["sources"] if p.endswith(".cc")]
    if set(sources) != set(spec["sources"]):
        raise ValueError("Unexpected V8 generator source inventory")
    definitions = value("defines")
    if not {"V8_ENABLE_SANDBOX", "V8_TEMPORAL_SUPPORT", "V8_USE_PERFETTO", "V8_INTL_SUPPORT", "V8_TARGET_ARCH_X64", "V8_TARGET_OS_LINUX"}.issubset(definitions):
        raise ValueError("Expected Electron Linux AMD64 V8 profile")
    flags, omitted = [], []
    for flag in value("cflags") + value("cflags_cc"):
        if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
            omitted.append(flag)
        else:
            flags.append(flag)
    if "-fno-exceptions" not in flags or "-fno-rtti" not in flags:
        raise ValueError("Unexpected V8 generator language profile")
    action = graph["targets"]["//v8:" + spec["action"]]
    if action["type"] != "action" or action["script"] != "//v8/tools/run.py" or action["deps"] != ["//v8:" + spec["tool"]] or action.get("inputs") or action.get("sources"):
        raise ValueError("Unexpected V8 generation action")
    output = spec["output"]
    if action["args"] != ["./" + spec["tool"], "gen/v8/" + output] or action["outputs"] != ["//out/bazel-import/gen/v8/" + output]:
        raise ValueError("Unexpected V8 generation outputs")
    return {
        "srcs": sources,
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


def main(default_generator=None):
    parser = argparse.ArgumentParser(description=__doc__)
    if default_generator is None:
        parser.add_argument("--generator", choices=GENERATORS, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    name = default_generator or args.generator
    spec = GENERATORS[name]
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), name)
    args.output.write_text('"""' + spec["title"] + ' from Electron 39 Linux AMD64 GN capture."""\n\n' + spec["variable"] + '_PROFILE_SHA256 = ' + repr(hashlib.sha256(content).hexdigest()) + '\n\n' + spec["variable"] + '_GENERATOR = ' + json.dumps(profile, indent=4) + '\n')


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Capture the complete Electron Torque compiler and generation action."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def capture(graph):
    def value(target, key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    libraries = {}
    toolchain = {"//buildtools/third_party/libc++:custom_headers", "//buildtools/third_party/libc++:libcxx_headers"}
    expected_deps = {
        "torque_base": toolchain | {"//v8:v8_config_headers", "//v8:v8_flags", "//v8:v8_libbase", "//v8:v8_shared_internal_headers"},
        "torque": toolchain | {"//build/config:executable_deps", "//build/win:default_exe_manifest", "//v8:torque_base", "//v8:v8_dump_build_config"},
    }
    for name in ("torque_base", "torque"):
        target = graph["targets"]["//v8:" + name]
        if target["type"] != ("executable" if name == "torque" else "source_set"):
            raise ValueError("Unexpected Torque compiler target kind")
        if set(target.get("deps", [])) != expected_deps[name]:
            raise ValueError("Untranslated Torque compiler dependency")
        sources = [path for path in target["sources"] if path.endswith(".cc")]
        if not sources or any(not path.startswith("//v8/src/torque/") for path in sources):
            raise ValueError("Unexpected Torque source inventory")
        flags, omitted = [], []
        for flag in value(target, "cflags") + value(target, "cflags_cc"):
            if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                omitted.append(flag)
            else:
                flags.append(flag)
        definitions = value(target, "defines")
        required = {"V8_ENABLE_SANDBOX", "V8_TEMPORAL_SUPPORT", "V8_USE_PERFETTO", "V8_INTL_SUPPORT", "V8_TARGET_ARCH_X64", "V8_TARGET_OS_LINUX"}
        if not required.issubset(definitions) or "-fexceptions" not in flags or "-frtti" not in flags:
            raise ValueError("Expected complete Electron Linux AMD64 Torque profile")
        libraries[name] = {
            "srcs": [path.removeprefix("//v8/") for path in sources],
            "copts": flags,
            "defines": [definition.replace('"', '\\"') for definition in definitions],
            "gn_defines": definitions,
            "gn_deps": target.get("deps", []),
            "gn_include_dirs": value(target, "include_dirs"),
            "gn_ldflags": value(target, "ldflags"),
            "omitted_toolchain_and_diagnostic_flags": omitted,
        }
    action = graph["targets"]["//v8:run_torque"]
    if action["script"] != "//v8/tools/run.py" or action["deps"] != ["//v8:torque"] or action.get("inputs"):
        raise ValueError("Unexpected Torque action dependencies")
    if action["args"][:5] != ["./torque", "-o", "gen/v8/torque-generated", "-v8-root", "../../v8"]:
        raise ValueError("Unexpected Torque generation arguments")
    sources = action["args"][5:]
    if len(set(sources)) != len(sources) or {"//v8/" + path for path in sources} != set(action["sources"]):
        raise ValueError("Torque argument order does not cover captured sources")
    if any(not path.endswith(".tq") for path in sources):
        raise ValueError("Expected Torque source arguments")
    prefix = "//out/bazel-import/gen/v8/"
    if any(not path.startswith(prefix + "torque-generated/") for path in action["outputs"]):
        raise ValueError("Unexpected Torque output prefix")
    return libraries, {"sources": sources, "outputs": [path.removeprefix(prefix) for path in action["outputs"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    libraries, action = capture(json.loads(gzip.decompress(content)))
    args.output.write_text('"""Complete Torque profile from Electron 39 Linux AMD64 GN capture."""\n\nTORQUE_PROFILE_SHA256 = ' + repr(hashlib.sha256(content).hexdigest()) + '\n\nTORQUE_LIBRARIES = ' + json.dumps(libraries, indent=4) + '\n\nTORQUE_RUN = ' + json.dumps(action, indent=4) + '\n')


if __name__ == "__main__":
    main()

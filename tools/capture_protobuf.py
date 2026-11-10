# SPDX-License-Identifier: MIT
"""Capture matching Protobuf runtime/compiler and its original plugin dependency."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_target import LinuxGraph, builtins_archive


PREFIX = "//third_party/protobuf:"
JS = "//third_party/protobuf-javascript:protoc-gen-js"
JS_REVISION = "e6d763860001ba1a76a63adcff5efb12b1c96024"
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers")}
TOOLCHAIN.add("//build/config:executable_deps")
ABSEIL = "//third_party/abseil-cpp:absl"
ROOTS = {"protobuf": "third_party/protobuf", "javascript": "third_party/protobuf-javascript/src"}


def capture(graph, chromium, javascript, target_arch="x64", role="target"):
    scope = LinuxGraph(graph, target_arch)
    root_label = scope.resolve(PREFIX + ("protoc" if role == "execution" or target_arch == "x64" and role == "target" else "protobuf_lite"), role)
    abseil_label = scope.resolve(ABSEIL, role)
    toolchain = {label for label in graph["targets"] if label.split("(")[0] in TOOLCHAIN}
    if "Version: 32.0\n" not in (chromium / "third_party/protobuf/README.chromium").read_text():
        raise ValueError("Expected Electron's embedded Protobuf 32.0")
    deps_text = (chromium / "DEPS").read_text()
    if "'/external/github.com/protocolbuffers/protobuf-javascript' + '@' + '" + JS_REVISION + "'" not in deps_text:
        raise ValueError("Protobuf JavaScript DEPS pin changed")
    targets = graph["targets"]

    def value(target, key):
        result = target.get(key, [])
        return graph["pool"][result["pool"]] if isinstance(result, dict) else result

    labels, pending = set(), [root_label]
    while pending:
        label = pending.pop()
        if label in labels or label in toolchain or label == abseil_label:
            continue
        if label.split("(")[0] == "//build/win:default_exe_manifest":
            target = targets[label]
            if target["type"] != "group" or target.get("deps"):
                raise ValueError("Unexpected nonempty Linux manifest dependency")
            continue
        if not label.startswith(PREFIX) and label.split("(")[0] != JS:
            raise ValueError("Untranslated Protobuf dependency: " + label)
        if scope.resolve(label.split("(")[0], role) != label:
            raise ValueError("Protobuf dependency crosses compiler role")
        labels.add(label)
        pending.extend(targets[label].get("deps", []))
    libraries, files = {}, set()
    for root, logical in [(chromium / "third_party/protobuf", "third_party/protobuf"), (javascript, "third_party/protobuf-javascript/src")]:
        files.update(logical + "/" + path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".inc", ".proto"))
        files.update(logical + "/" + path.name for path in root.iterdir() if path.is_file() and path.name.startswith(("LICENSE", "COPYING", "NOTICE")))
    for label in sorted(labels):
        target = targets[label]
        architecture = scope.architecture(label)
        bare = label.split("(")[0]
        if target["type"] not in ("source_set", "static_library", "executable") or target["type"] == "executable" and architecture != "x64":
            raise ValueError("Unexpected Protobuf native profile")
        sources = target.get("sources", [])
        if any(not path.startswith(("//third_party/protobuf/", "//third_party/protobuf-javascript/src/")) or not path.endswith((".cc", ".c", ".h", ".inc")) for path in sources):
            raise ValueError("Unexpected Protobuf source path")
        files.update(path[2:] for path in sources)
        units = [path[2:] for path in sources if path.endswith((".cc", ".c"))]
        language = "cflags_c" if units and units[0].endswith(".c") else "cflags_cc"
        if any(path.endswith(".c") != (language == "cflags_c") for path in units):
            raise ValueError("Mixed C/C++ Protobuf library")
        flags, omitted = [], []
        for flag in value(target, "cflags") + value(target, language):
            if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                omitted.append(flag)
            else:
                flags.append(flag)
        if any(lib not in (builtins_archive(architecture), "dl", "pthread", "rt") for lib in value(target, "libs")):
            raise ValueError("Unexpected Protobuf link library")
        if bare != PREFIX + "utf8_range" and not {"GOOGLE_PROTOBUF_NO_RTTI", "PROTOBUF_INTERNAL_BOUNDS_CHECK_MODE_ABORT"}.issubset(value(target, "defines")):
            raise ValueError("Missing captured Protobuf safety profile")
        libraries[label] = {
            "name": "protoc_js" if bare == JS else bare.removeprefix(PREFIX),
            "architecture": architecture,
            "toolchain": target["toolchain"],
            "kind": target["type"],
            "srcs": units,
            "copts": flags,
            "defines": [item.replace('"', '\\"') for item in value(target, "defines")],
            "deps": [dep for dep in target.get("deps", []) if dep in labels],
            "abseil": abseil_label in target.get("deps", []),
            "gn_deps": target.get("deps", []),
            "gn_include_dirs": value(target, "include_dirs"),
            "gn_ldflags": value(target, "ldflags"),
            "gn_libs": value(target, "libs"),
            "omitted_toolchain_and_diagnostic_flags": omitted,
        }
    abseil = targets[scope.resolve("//third_party/abseil-cpp:absl_component_deps", role)]
    if abseil["type"] != "group" or any(not dep.startswith("//third_party/abseil-cpp/absl/") for dep in abseil["deps"]):
        raise ValueError("Unexpected captured Abseil aggregate")
    if any(scope.resolve(dep.split("(")[0], role) != dep for dep in abseil["deps"]):
        raise ValueError("Abseil aggregate crosses compiler role")
    for logical in files:
        physical = javascript / logical.removeprefix("third_party/protobuf-javascript/src/") if logical.startswith("third_party/protobuf-javascript/src/") else chromium / logical
        if not physical.is_file():
            raise ValueError("Missing original Protobuf input: " + logical)
    return {"target_arch": target_arch, "role": role, "root": root_label, "roots": ROOTS, "libraries": libraries, "files": sorted(files), "abseil_gn_deps": abseil["deps"], "abseil_deps": (["@electron_abseil_sources//" + dep.removeprefix("//third_party/abseil-cpp/") for dep in abseil["deps"]] if target_arch == "x64" and role == "target" else None), "javascript_revision": JS_REVISION, "version": "32.0", "toolchain_deps": sorted(toolchain)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--chromium-root", type=Path, required=True)
    parser.add_argument("--javascript-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-arch", choices=("x64", "arm64"), default="x64")
    parser.add_argument("--role", choices=("target", "execution", "snapshot"), default="target")
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), args.chromium_root, args.javascript_root, args.target_arch, args.role)
    profile["graph_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.write_text(json.dumps(profile, indent=2) + "\n")


if __name__ == "__main__":
    main()

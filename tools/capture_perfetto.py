# SPDX-License-Identifier: MIT
"""Capture complete Electron Perfetto runtime, plugins and native generators."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_target import LinuxGraph, builtins_archive


PREFIX = "//third_party/perfetto"
BUILD = "//out/bazel-import/"
ROOT = PREFIX + ":libperfetto"
JSONCPP = "//third_party/jsoncpp:jsoncpp"
EXTERNAL = {
    "//third_party/protobuf:protoc": "@electron_protobuf_sources//:protoc",
    "//third_party/protobuf:protoc_lib": "@electron_protobuf_sources//:protoc_lib",
    "//third_party/zlib:zlib": "@electron_v8_support_sources//:zlib",
}
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers")}
TOOLCHAIN.add("//build/config:executable_deps")
SCRIPTS = {
    "//tools/protoc_wrapper/protoc_wrapper.py",
    PREFIX + "/gn/write_buildflag_header.py",
    PREFIX + "/tools/gen_cc_proto_descriptor.py",
    PREFIX + "/tools/gen_tp_table_headers.py",
    PREFIX + "/tools/touch_file.py",
}


def capture(graph, chromium, perfetto, jsoncpp, target_arch="x64", role="target"):
    scope = LinuxGraph(graph, target_arch)
    root = scope.resolve(ROOT, role)
    protoc = scope.resolve("//third_party/protobuf:protoc", "execution")
    external = {label: (EXTERNAL[label] if target_arch == "x64" and role == "target" and label in EXTERNAL else None)
                for label in graph["targets"] if label.split("(")[0] in EXTERNAL}
    toolchain = {label for label in graph["targets"] if label.split("(")[0] in TOOLCHAIN}
    deps = (chromium / "DEPS").read_text()
    if "42e892d96e47b1f6e29844cc705e148ec4856448" not in deps:
        raise ValueError("JsonCpp DEPS pin changed")
    targets, seen, pending = graph["targets"], set(), [root]
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in toolchain:
            continue
        if not label.startswith(PREFIX) and label.split("(")[0] != JSONCPP:
            raise ValueError("Untranslated Perfetto dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}

    def value(target, key):
        result = target.get(key, [])
        return graph["pool"][result["pool"]] if isinstance(result, dict) else result

    def physical(path):
        if path.startswith("third_party/perfetto/"):
            return perfetto / path.removeprefix("third_party/perfetto/")
        if path.startswith("third_party/jsoncpp/source/"):
            return jsoncpp / path.removeprefix("third_party/jsoncpp/source/")
        return chromium / path

    files, headers, actions, libraries = set(), [], {}, {}
    for directory, prefix in [(perfetto, "third_party/perfetto/"), (jsoncpp, "third_party/jsoncpp/source/")]:
        paths = [prefix + path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file() and path.suffix in (".h", ".inc", ".inl")]
        files.update(paths)
        headers += paths
        files.update(prefix + path.name for path in directory.iterdir() if path.is_file() and path.name.startswith(("LICENSE", "COPYING", "NOTICE")))
    python = sorted("third_party/perfetto/" + path.relative_to(perfetto).as_posix() for directory in ("python/generators/trace_processor_table", "src/trace_processor/tables") for path in (perfetto / directory).rglob("*.py"))
    tools = {BUILD + targets[label]["outputs"][0].removeprefix(BUILD): label for label in seen if targets[label]["type"] == "executable"}
    for output in targets[protoc]["outputs"]:
        if not output.startswith(BUILD):
            raise ValueError("Unexpected protoc output")
        tools[output] = protoc
    producers = {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] == "action":
            if target["script"] not in SCRIPTS:
                raise ValueError("Unknown Perfetto generator")
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate Perfetto output")
                producers[output] = label
    for label in sorted(seen):
        target = targets[label]
        architecture = scope.architecture(label)
        if target["type"] == "executable" and architecture != "x64":
            raise ValueError("Perfetto generators must execute on Linux x64")
        kind = target["type"]
        record = {"name": names[label], "kind": kind, "gn_deps": target.get("deps", []),
                  "architecture": architecture, "toolchain": target["toolchain"]}
        if kind == "action":
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [target["script"]])
            if target["script"].endswith("/gen_tp_table_headers.py"):
                inputs.update("//" + path for path in python)
            tool_inputs, source_inputs = {}, []
            for path in sorted(inputs):
                if path in tools:
                    tool_inputs[path.removeprefix("//")] = tools[path]
                elif path.startswith(BUILD):
                    if path not in producers:
                        raise ValueError("Unknown generated Perfetto input: " + path)
                    source_inputs.append(path)
                else:
                    if not path.startswith((PREFIX + "/", "//tools/protoc_wrapper/", "//third_party/protobuf/src/")):
                        raise ValueError("Unmapped Perfetto generator input")
                    source_inputs.append(path)
                    if not path.startswith("//third_party/protobuf/"):
                        files.add(path[2:])
            record.update(script=target["script"][2:], args=target.get("args", []), response=target.get("response_file_contents", []), inputs=source_inputs, tools=tool_inputs, outputs=target["outputs"])
            if any("{{" in arg and arg != "{{response_file_name}}" for arg in record["args"]):
                raise ValueError("Unknown GN generator placeholder")
            record["generated_include_roots"] = sorted({path.removeprefix(BUILD).split("gen/")[0] + "gen"
                                                         for path in target["outputs"] if "gen/" in path.removeprefix(BUILD)})
            actions[label] = record
        elif kind in ("source_set", "static_library", "executable", "group"):
            sources = target.get("sources", [])
            units = [path for path in sources if path.endswith((".cc", ".cpp", ".c"))]
            if any(not path.startswith((PREFIX + "/", "//third_party/jsoncpp/source/", BUILD)) for path in sources):
                raise ValueError("Unexpected Perfetto source inventory")
            for path in sources:
                if path.startswith(BUILD):
                    if path not in producers:
                        raise ValueError("Unowned generated Perfetto source: " + path)
                else:
                    files.add(path[2:])
            if any(path.endswith(".c") for path in units):
                raise ValueError("Unexpected C target requires separate language profile")
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
                    raise ValueError("Unexpected Perfetto include root")
            if any(lib not in ("dl", "pthread", "rt", builtins_archive(architecture)) for lib in value(target, "libs")):
                raise ValueError("Untranslated Perfetto link library")
            record.update(srcs=units, generated_headers=[path for path in sources if path.startswith(BUILD) and path.endswith(".h")], copts=flags, defines=[item.replace('"', '\\"') for item in value(target, "defines")], includes=includes, gn_include_dirs=value(target, "include_dirs"), gn_ldflags=value(target, "ldflags"), libs=value(target, "libs"), omitted_toolchain_and_diagnostic_flags=omitted)
            libraries[label] = record
        else:
            raise ValueError("Untranslated Perfetto target kind: " + kind)
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original Perfetto input: " + path)
    return {"target_arch": target_arch, "role": role, "root": root, "names": names, "libraries": libraries, "actions": actions, "producers": producers, "files": sorted(files), "headers": sorted(headers), "external": {label: external[label] for label in sorted({dep for label in seen for dep in targets[label].get("deps", []) if dep in external})}, "external_executables": [protoc], "toolchain_deps": sorted(toolchain)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--chromium-root", type=Path, required=True)
    parser.add_argument("--perfetto-root", type=Path, required=True)
    parser.add_argument("--jsoncpp-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-arch", choices=("x64", "arm64"), default="x64")
    parser.add_argument("--role", choices=("target", "execution", "snapshot"), default="target")
    args = parser.parse_args()
    content = args.graph.read_bytes()
    result = capture(json.loads(gzip.decompress(content)), args.chromium_root, args.perfetto_root, args.jsoncpp_root, args.target_arch, args.role)
    result["graph_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Capture patched libnode, original inspector generators and compression closure."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_node_deps import LIBRARIES

ROOT = "//third_party/electron_node:libnode"
BUILD = "//out/bazel-import/"
NODE = "third_party/electron_node/"
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers")}
REUSE = {
    "//base:base": "@electron_base_sources//:base",
    "//third_party/boringssl:boringssl": "@electron_boringssl_sources//:ssl",
    "//third_party/electron_node/deps/uv:uv": "@electron_node_sources//:libuv",
    "//third_party/icu:icu": "@electron_icu_sources//:icu",
    "//third_party/simdutf:simdutf": "@electron_v8_support_sources//:simdutf",
    "//third_party/zlib:zlib": "@electron_v8_support_sources//:zlib",
    "//v8:v8": "@electron_v8_engine_sources//:v8",
    "//v8:v8_libplatform": "@electron_v8_engine_sources//:platform",
}
REUSE.update({"//" + NODE + "deps/" + name + ":" + name: "@electron_node_sources//:node_deps_" + name for name in LIBRARIES})
GENERATORS = {"//electron:electron_js2c", "//third_party/electron_node:run_node_js2c"}
GENERATED_FILES = {
    BUILD + "gen/electron_natives.cc": "@electron//source:electron_natives",
    BUILD + "gen/third_party/electron_node/node_javascript.cc": "@electron//source:node_javascript",
}
ALIASES = {NODE + "deps/v8/include/js_protocol.pdl": "v8/include/js_protocol.pdl"}
SCRIPTS = {
    "//third_party/inspector_protocol/code_generator.py",
    "//third_party/inspector_protocol/concatenate_protocols.py",
    "//v8/third_party/inspector_protocol/convert_protocol_to_json.py",
    "//third_party/electron_node/tools/compress_json.py",
}


def capture(graph, chromium, node, v8, zstd):
    if "89d685e42dbcf815a16ed0fcd7d050ef74ccad96" not in (chromium / "DEPS").read_text():
        raise ValueError("Zstd DEPS pin changed")
    # Node exposes compression; captured GN only links the decoder.
    targets, seen, pending = graph["targets"], set(), [ROOT, "//third_party/zstd:compress"]
    while pending:
        label = pending.pop()
        if label in seen or label in REUSE or label in TOOLCHAIN or label in GENERATORS:
            continue
        if label != ROOT and not label.startswith(("//" + NODE, "//third_party/brotli:", "//third_party/zstd:", "//third_party/inspector_protocol:")):
            raise ValueError("Untranslated libnode dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}

    def value(target, key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    def physical(path):
        path = ALIASES.get(path, path)
        for prefix, directory in [(NODE, node), ("v8/", v8), ("third_party/zstd/src/", zstd)]:
            if path.startswith(prefix):
                return directory / path.removeprefix(prefix)
        return chromium / path

    files, headers, python = set(), set(), set()
    for directory, prefix in [
        (node / "src", NODE + "src/"),
        (chromium / "third_party/brotli", "third_party/brotli/"),
        (chromium / "third_party/inspector_protocol", "third_party/inspector_protocol/"),
        (zstd / "lib", "third_party/zstd/src/lib/"),
    ]:
        inventory = [prefix + path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file() and path.suffix in (".h", ".hpp", ".inc", ".inl")]
        if not inventory:
            raise ValueError("Missing public header inventory: " + prefix)
        headers.update(inventory)
    files.update(headers)
    for directory, prefix in [
        (chromium / "third_party/inspector_protocol", "third_party/inspector_protocol/"),
        (v8 / "third_party/inspector_protocol", "v8/third_party/inspector_protocol/"),
        (chromium / "third_party/jinja2", "third_party/jinja2/"),
        (chromium / "third_party/markupsafe", "third_party/markupsafe/"),
    ]:
        python.update(prefix + path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file() and path.suffix in (".py", ".template"))
        files.update(prefix + path.name for path in directory.iterdir() if path.is_file() and path.name.startswith(("LICENSE", "COPYING", "NOTICE")))
    files.update([NODE + "LICENSE", "third_party/zstd/src/LICENSE", "third_party/zstd/src/COPYING", "third_party/brotli/LICENSE"])
    def outputs_for(target):
        outputs = list(target.get("outputs", []))
        if target.get("script") == "//third_party/inspector_protocol/code_generator.py":
            outputs.append(BUILD + "gen/third_party/electron_node/src/node/inspector/protocol/Runtime.h")
        return outputs

    producers, actions, libraries = {}, {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "action_foreach"):
            for output in outputs_for(target):
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate libnode output")
                producers[output] = label
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 libnode profile")
        kind = target["type"]
        record = {"name": names[label], "kind": kind, "gn_deps": target.get("deps", [])}
        if label == ROOT:
            record["native_extra_deps"] = ["//third_party/zstd:compress"]
        if kind in ("action", "action_foreach"):
            if target["script"] not in SCRIPTS:
                raise ValueError("Unknown libnode generator")
            common = set(target.get("inputs", []) + [target["script"]])
            if target["script"] == "//third_party/inspector_protocol/code_generator.py":
                common.update(["//" + NODE + "src/inspector/node_protocol.pdl", "//" + NODE + "deps/v8/include/js_protocol.pdl"])
            if "inspector_protocol/" in target["script"]:
                common.update("//" + path for path in python)
            runs = []
            for index, source in enumerate(target["sources"] if kind == "action_foreach" else [None]):
                inputs = common | ({source} if source else set(target.get("sources", [])))
                args = target.get("args", [])
                outputs = outputs_for(target)
                if source:
                    args = [arg.replace("{{source}}", "../../" + source[2:]).replace("{{source_name_part}}", Path(source).stem) for arg in args]
                    outputs = [BUILD + "gen/third_party/electron_node/src/" + Path(source).stem + ".json"]
                    if outputs[0] != target["outputs"][index]:
                        raise ValueError("Unexpected inspector foreach output")
                if any("{{" in arg for arg in args):
                    raise ValueError("Untranslated inspector placeholder")
                for path in inputs:
                    if path.startswith(BUILD):
                        if path not in producers and path not in GENERATED_FILES:
                            raise ValueError("Unowned libnode generator input")
                    else:
                        files.add(path[2:])
                runs.append({"inputs": sorted(inputs), "outputs": outputs, "args": args})
            record.update(script=target["script"][2:], runs=runs, outputs=outputs_for(target), gn_outputs=target["outputs"])
            actions[label] = record
        elif kind in ("static_library", "source_set"):
            sources = target.get("sources", [])
            if any(Path(path).suffix not in (".h", ".inc", ".cc", ".cpp", ".c", ".S", ".s") for path in sources):
                raise ValueError("Untranslated libnode source language")
            for path in sources:
                if path.startswith(BUILD):
                    if path not in producers and path not in GENERATED_FILES:
                        raise ValueError("Unowned libnode source: " + path)
                else:
                    files.add(path[2:])
            flags, omitted = {}, []
            for language, key in [("cc", "cflags_cc"), ("c", "cflags_c"), ("asm", "asmflags")]:
                kept = []
                for flag in value(target, "cflags") + value(target, key):
                    if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                        omitted.append(flag)
                    else:
                        kept.append(flag)
                flags[language] = kept
            includes = []
            for path in value(target, "include_dirs"):
                if path == "//buildtools/third_party/libc++/":
                    continue
                if path.startswith(BUILD):
                    includes.append(path.removeprefix(BUILD).rstrip("/") or ".")
                elif path.startswith("//"):
                    includes.append(path[2:].rstrip("/") or ".")
                else:
                    raise ValueError("Untranslated libnode include root")
            libs = value(target, "libs")
            if set(libs) - {"m", "dl", "rt", "pthread", "atomic", "glib-2.0", "gmodule-2.0", "gobject-2.0", "gthread-2.0", "$LLVM_ROOT/lib/clang/23/lib/x86_64-unknown-linux-gnu/libclang_rt.builtins.a"}:
                raise ValueError("Untranslated libnode link library")
            record.update(srcs=[p for p in sources if p.endswith((".cc", ".cpp"))], c_srcs=[p for p in sources if p.endswith(".c")], asm_srcs=[p for p in sources if p.endswith((".S", ".s"))], generated_headers=[p for p in sources if p.startswith(BUILD) and p.endswith((".h", ".inc"))], copts=flags["cc"], c_copts=flags["c"], asm_copts=flags["asm"], includes=includes, defines=[d.replace('"', '\\"') for d in value(target, "defines")], libs=libs, gn_include_dirs=value(target, "include_dirs"), gn_ldflags=value(target, "ldflags"), omitted_toolchain_and_diagnostic_flags=sorted(set(omitted)))
            libraries[label] = record
        else:
            raise ValueError("Untranslated libnode target kind")
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original libnode input: " + path)
    header_families = {name: sorted(path for path in headers if path.startswith(prefix)) for name, prefix in {"node": NODE, "brotli": "third_party/brotli/", "zstd": "third_party/zstd/", "inspector": "third_party/inspector_protocol/"}.items()}
    return {"root": ROOT, "native_library_replacements": {"atomic": "@llvm//runtimes/compiler-rt:clang_rt.builtins.static"}, "aliases": ALIASES, "names": names, "libraries": libraries, "actions": actions, "producers": producers, "files": sorted(files), "headers": header_families, "external": REUSE, "generated_files": GENERATED_FILES, "generator_deps": sorted(GENERATORS), "toolchain_deps": sorted(TOOLCHAIN)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["graph", "chromium-root", "node-root", "v8-root", "zstd-root", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    result = capture(json.loads(gzip.decompress(content)), args.chromium_root, args.node_root, args.v8_root, args.zstd_root)
    result["graph_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

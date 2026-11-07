# SPDX-License-Identifier: MIT
"""Capture the complete patched V8 engine, inspector and snapshot graph."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


BUILD = "//out/bazel-import/"
ROOTS = ["//v8:v8", "//v8:v8_libplatform"]
REUSE = {
    "//v8:v8_libbase": "@electron_v8_sources//:libbase",
    "//v8:libm": "@electron_v8_sources//:libm",
    "//third_party/abseil-cpp:absl": "@electron_protobuf_sources//:abseil",
    "//third_party/dragonbox:dragonbox": "@electron_v8_support_sources//:dragonbox",
    "//third_party/fast_float:fast_float": "@electron_v8_support_sources//:fast_float",
    "//third_party/highway:libhwy": "@electron_v8_support_sources//:highway",
    "//third_party/simdutf:simdutf": "@electron_v8_support_sources//:simdutf",
    "//third_party/zlib:zlib": "@electron_v8_support_sources//:zlib",
    "//third_party/zlib/google:compression_utils_portable": "@electron_v8_support_sources//:compression_utils_portable",
    "//third_party/icu:icu": "@electron_icu_sources//:icu",
    "//third_party/perfetto:libperfetto": "@electron_perfetto_native_sources//:perfetto",
    "//third_party/rust/temporal_capi:temporal_capi": "@electron_rust_sources//:temporal_capi",
}
GENERATORS = {
    "//v8:run_torque": "@electron//source:v8_torque",
    "//v8:generate_bytecode_builtins_list": "@electron//source:v8_bytecodes",
    "//v8:run_gen-regexp-special-case": "@electron//source:v8_regexp",
}
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers")}
TOOLCHAIN.update(["//build/config:executable_deps", "//build/win:default_exe_manifest", "//third_party/icu:copy_icudata"])


def capture(graph, v8, chromium, fp16):
    if "3d2de1816307bac63c16a297e8c4dc501b4076df" not in (chromium / "DEPS").read_text():
        raise ValueError("FP16 DEPS pin changed")
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    while pending:
        label = pending.pop()
        if label in seen or label in REUSE or label in TOOLCHAIN:
            continue
        if not label.startswith("//v8") and label != "//third_party/fp16:fp16":
            raise ValueError("Untranslated V8 engine dependency: " + label)
        seen.add(label)
        if label not in GENERATORS:
            pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}

    def value(target, key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    def flags(target, language):
        kept, omitted = [], []
        for flag in value(target, "cflags") + value(target, language):
            if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                omitted.append(flag)
            else:
                kept.append(flag)
        return kept, omitted

    def physical(path):
        if path.startswith("v8/"):
            return v8 / path.removeprefix("v8/")
        if path.startswith("third_party/fp16/src/"):
            return fp16 / path.removeprefix("third_party/fp16/src/")
        return chromium / path

    files, headers, actions, libraries, reused, producers = set(), [], {}, {}, {}, {}
    for root, prefix in [(v8, "v8/"), (fp16, "third_party/fp16/src/")]:
        inventory = [prefix + path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".inc", ".inl")]
        headers += inventory
        files.update(inventory)
        files.update(prefix + path.name for path in root.iterdir() if path.is_file() and path.name.startswith(("LICENSE", "COPYING", "NOTICE")))
    python = []
    for root, prefix in [(v8 / "third_party/inspector_protocol", "v8/third_party/inspector_protocol/"), (chromium / "third_party/jinja2", "third_party/jinja2/"), (chromium / "third_party/markupsafe", "third_party/markupsafe/")]:
        python += [prefix + path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".py", ".template")]
        files.update(prefix + path.name for path in root.iterdir() if path.is_file() and path.name.startswith(("LICENSE", "COPYING", "NOTICE")))
    for label in sorted(seen):
        target = targets[label]
        if target["type"] == "action":
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate V8 generated output")
                producers[output] = label
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured V8 Linux AMD64 profile")
        record = {"name": names[label], "kind": target["type"], "gn_deps": target.get("deps", [])}
        if label in GENERATORS:
            outputs = target["outputs"]
            if any(not path.startswith(BUILD + "gen/v8/") for path in outputs):
                raise ValueError("Unexpected reused V8 generator output layout")
            record.update(target=GENERATORS[label], outputs={path.removeprefix(BUILD): path.removeprefix(BUILD + "gen/v8/") for path in outputs})
            reused[label] = record
        elif target["type"] == "action":
            if target["script"] not in ("//v8/tools/run.py", "//v8/tools/testrunner/utils/dump_build_config.py", "//v8/third_party/inspector_protocol/code_generator.py", "//v8/third_party/inspector_protocol/check_protocol_compatibility.py"):
                raise ValueError("Unknown V8 engine action")
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [target["script"]])
            if "inspector_protocol/" in target["script"]:
                inputs.update("//" + path for path in python)
            for path in inputs:
                if not path.startswith(BUILD):
                    files.add(path[2:])
                elif path != BUILD + "icudtl.dat" and path not in producers:
                    raise ValueError("Unowned generated V8 action input")
            tools = {"out/bazel-import/mksnapshot": "//v8:mksnapshot"} if label == "//v8:run_mksnapshot_default" else {}
            record.update(script=target["script"][2:], args=target.get("args", []), response=target.get("response_file_contents", []), inputs=sorted(inputs), tools=tools, outputs=target["outputs"])
            actions[label] = record
        elif target["type"] in ("group", "source_set", "static_library", "executable"):
            sources = target.get("sources", [])
            for path in sources:
                if path.startswith(BUILD):
                    if path not in producers:
                        raise ValueError("Unowned generated V8 source: " + path)
                elif path.startswith(("//v8/", "//third_party/fp16/src/")):
                    files.add(path[2:])
                else:
                    raise ValueError("Unexpected V8 source path")
            includes = []
            for path in value(target, "include_dirs"):
                if path == "//buildtools/third_party/libc++/":
                    continue
                if path.startswith(BUILD):
                    includes.append(path.removeprefix(BUILD).rstrip("/") or ".")
                elif path.startswith("//"):
                    includes.append(path[2:].rstrip("/") or ".")
                else:
                    raise ValueError("Unexpected V8 include root")
            copts, omitted = flags(target, "cflags_cc")
            asmopts, asm_omitted = flags(target, "asmflags")
            if any(lib not in ("dl", "pthread", "rt", "m", "$LLVM_ROOT/lib/clang/23/lib/x86_64-unknown-linux-gnu/libclang_rt.builtins.a") for lib in value(target, "libs")):
                raise ValueError("Unexpected V8 link library")
            record.update(srcs=[path for path in sources if path.endswith((".cc", ".cpp"))], asm_srcs=[path for path in sources if path.endswith((".S", ".s"))], generated_headers=[path for path in sources if path.startswith(BUILD) and path.endswith((".h", ".inc"))], copts=copts, asm_copts=asmopts, defines=[item.replace('"', '\\"') for item in value(target, "defines")], includes=includes, libs=value(target, "libs"), gn_include_dirs=value(target, "include_dirs"), gn_ldflags=value(target, "ldflags"), omitted_toolchain_and_diagnostic_flags=omitted, omitted_asm_toolchain_and_diagnostic_flags=asm_omitted)
            libraries[label] = record
        else:
            raise ValueError("Untranslated V8 target kind")
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original V8 input: " + path)
    return {"roots": ROOTS, "names": names, "libraries": libraries, "actions": actions, "reused_generators": reused, "producers": producers, "files": sorted(files), "headers": sorted(headers), "external": REUSE, "toolchain_deps": sorted(TOOLCHAIN)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--v8-root", type=Path, required=True)
    parser.add_argument("--chromium-root", type=Path, required=True)
    parser.add_argument("--fp16-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    result = capture(json.loads(gzip.decompress(content)), args.v8_root, args.chromium_root, args.fp16_root)
    result["graph_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

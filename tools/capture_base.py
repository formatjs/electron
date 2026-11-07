# SPDX-License-Identifier: MIT
"""Capture matching Chromium base, original generators and Rust CXX bridges."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from capture_temporal import NATIVE_CPP

BUILD = "//out/bazel-import/"
ROOT = "//base:base"
CFG = "//build/rust/gni_impl:rustc_print_cfg"
CXX = "//third_party/rust/cxxbridge_cmd/v1:cxxbridge(//build/toolchain/linux:clang_x64_for_rust_host_build_tools)"
SCRIPTS = {
    "//build/write_buildflag_header.py", "//base/write_build_date_header.py",
    "//build/util/version.py", "//tools/protoc_wrapper/protoc_wrapper.py",
    "//electron/script/generate-mas-config.py",
    "//third_party/rust/cxx/chromium_integration/run_cxxbridge.py",
}
TOOLCHAIN = {"//buildtools/third_party/libc++:" + n for n in ("all_modules", "custom_headers", "libcxx_headers")}
TOOLCHAIN.add("//build/config:executable_deps")


def capture(graph, chromium, boringssl, icu, perfetto_profile, rust_profile):
    for root, header in [(boringssl, "include/openssl/base.h"), (icu, "source/common/unicode/locid.h")]:
        if not (root / header).is_file():
            raise ValueError("Missing pinned header source: " + header)
    targets = graph["targets"]
    external = {label: "@electron_perfetto_native_sources//:" + name for label, name in perfetto_profile["names"].items()}
    external.update({label: "@electron_rust_sources//:" + record["name"] for label, record in rust_profile["rust"].items()})
    for prefix, actual in [
        ("//base/allocator/partition_allocator:", "@electron_partition_alloc_sources//:partition_alloc"),
        ("//third_party/abseil-cpp:", "@electron_protobuf_sources//:abseil"),
        ("//third_party/icu:", "@electron_icu_sources//:icu"),
    ]:
        external.update({label: actual for label in targets if label.startswith(prefix)})
    external["//base/allocator/partition_allocator:raw_ptr"] = "@electron_partition_alloc_sources//:raw_ptr"
    external.update({"//third_party/zlib:zlib": "@electron_v8_support_sources//:zlib", "//third_party/boringssl:boringssl": "@electron_boringssl_sources//:ssl", "//third_party/protobuf:protoc": "@electron_protobuf_sources//:protoc"})
    seen, pending = set(), [ROOT] + list(NATIVE_CPP)
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}

    def value(target, key):
        result = target.get(key, [])
        return graph["pool"][result["pool"]] if isinstance(result, dict) else result

    files, headers = set(), set()
    for directory in ["base", "build", "third_party/abseil-cpp", "third_party/icu/source/common", "third_party/icu/source/i18n", "third_party/zlib", "third_party/modp_b64", "third_party/rust/cxx/v1", "third_party/rust/chromium_crates_io/vendor/cxx-v1", "third_party/rust/serde_json_lenient/v0_2/wrapper"]:
        for path in (chromium / directory).rglob("*"):
            if path.is_file() and path.suffix in (".h", ".inc", ".inl"):
                headers.add(path.relative_to(chromium).as_posix())
    headers.update("third_party/icu/" + path.relative_to(icu).as_posix() for directory in ["source/common", "source/i18n"] for path in (icu / directory).rglob("*.h"))
    headers.update("third_party/boringssl/src/" + path.relative_to(boringssl).as_posix() for path in (boringssl / "include").rglob("*.h"))
    headers.add("third_party/lss/linux_syscall_support.h")
    headers.add("testing/gtest/include/gtest/gtest_prod.h")
    files.update(headers)
    actions, libraries, copies, producers = {}, {}, {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "action_foreach", "copy"):
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate base output: " + output)
                producers[output] = label
    tool_paths = {BUILD + "protoc": "//third_party/protobuf:protoc", BUILD + "protozero_plugin": "//third_party/perfetto/src/protozero/protoc_plugin:protozero_plugin", BUILD + "clang_x64_for_rust_host_build_tools/cxxbridge": CXX}
    external_files = {}
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected Linux AMD64 base profile")
        kind = target["type"]
        record = {"name": names[label], "kind": kind, "gn_deps": target.get("deps", [])}
        if label == CFG:
            record.update(outputs=target["outputs"])
            actions[label] = record
            continue
        if kind in ("action", "action_foreach"):
            if target["script"] not in SCRIPTS:
                raise ValueError("Unknown base generator: " + target["script"])
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [target["script"]])
            args = target.get("args", [])
            if kind == "action_foreach":
                if len(target["sources"]) != 1:
                    raise ValueError("Expected single-source CXX bridge")
                source = target["sources"][0][2:]
                replacements = {"{{source_gen_dir}}": "gen/" + str(Path(source).parent), "{{source_file_part}}": Path(source).name, "{{source}}": "../../" + source}
                args = [arg for arg in args]
                for before, after in replacements.items():
                    args = [arg.replace(before, after) for arg in args]
                inputs.update(["//build/action_helpers.py", "//build/gn_helpers.py"])
            args = [arg.replace("$SOURCE_ROOT/out/bazel-import/", "") for arg in args]
            if any("{{" in arg and arg != "{{response_file_name}}" for arg in args):
                raise ValueError("Unknown base generator placeholder")
            tools, source_inputs = {}, []
            for path in sorted(inputs):
                if path in tool_paths:
                    tools[path[2:]] = tool_paths[path]
                elif path.startswith(BUILD):
                    if path not in producers:
                        raise ValueError("Unowned generated base input: " + path)
                    source_inputs.append(path)
                else:
                    source_inputs.append(path)
                    if path.startswith("//third_party/perfetto/"):
                        external_files[path] = "@electron_perfetto_native_sources//:" + path[2:]
                    elif path.startswith("//third_party/protobuf/"):
                        external_files[path] = "@electron_protobuf_sources//:" + path[2:]
                    else:
                        files.add(path[2:])
            record.update(script=target["script"][2:], args=args, response=target.get("response_file_contents", []), inputs=source_inputs, tools=tools, outputs=target["outputs"])
            actions[label] = record
        elif kind == "copy":
            if len(target["sources"]) != len(target["outputs"]):
                raise ValueError("Unmatched base copy")
            record.update(srcs=target["sources"], outputs=target["outputs"])
            copies[label] = record
        elif kind in ("static_library", "source_set", "group"):
            sources = target.get("sources", [])
            for path in sources:
                if path.startswith(BUILD):
                    if path not in producers:
                        raise ValueError("Unowned base source: " + path)
                else:
                    files.add(path[2:])
            common, omitted = [], []
            for flag in value(target, "cflags"):
                if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                    omitted.append(flag)
                else:
                    common.append(flag)
            language_flags = {}
            for language in ("c", "cc", "asm"):
                flags = []
                for flag in value(target, "asmflags" if language == "asm" else "cflags_" + language):
                    if flag == "-nostdinc++" or flag.startswith(("--sysroot=", "--target=", "-isystem../../")):
                        omitted.append(flag)
                    else:
                        flags.append(flag)
                language_flags[language] = common + flags
            includes = []
            for path in value(target, "include_dirs"):
                if path == "//buildtools/third_party/libc++/":
                    continue
                if path.startswith(BUILD):
                    includes.append(path.removeprefix(BUILD).rstrip("/") or ".")
                elif path.startswith("//"):
                    includes.append(path[2:].rstrip("/") or ".")
                else:
                    raise ValueError("Unexpected base include directory")
            libs = value(target, "libs")
            allowed = {"glib-2.0", "gmodule-2.0", "gobject-2.0", "gthread-2.0", "dl", "pthread", "rt", "$LLVM_ROOT/lib/clang/23/lib/x86_64-unknown-linux-gnu/libclang_rt.builtins.a"}
            if set(libs) - allowed:
                raise ValueError("Untranslated base native library: " + repr(set(libs) - allowed))
            record.update(srcs=[path for path in sources if path.endswith((".cc", ".cpp"))], c_srcs=[path for path in sources if path.endswith(".c")], asm_srcs=[path for path in sources if path.endswith((".S", ".s"))], generated_headers=[path for path in sources if path.startswith(BUILD) and path.endswith((".h", ".inc"))], copts=language_flags["cc"], c_copts=language_flags["c"], asm_copts=language_flags["asm"], defines=[item.replace('"', '\\"') for item in value(target, "defines")], includes=includes, libs=libs, gn_ldflags=value(target,"ldflags"), omitted_toolchain_and_diagnostic_flags=omitted)
            libraries[label] = record
        else:
            raise ValueError("Untranslated base target kind: " + kind)
    for path in files:
        if path.startswith(("electron/", "third_party/lss/", "third_party/boringssl/src/", "third_party/icu/", "testing/gtest/")):
            continue
        if not (chromium / path).is_file():
            raise ValueError("Missing original base input: " + path)
    used_external = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return {"root": ROOT, "names": names, "libraries": libraries, "actions": actions, "copies": copies, "producers": producers, "files": sorted(files), "headers": sorted(headers), "external": {label: external[label] for label in sorted(used_external)}, "external_files": external_files, "toolchain_deps": sorted(TOOLCHAIN)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--chromium-root", type=Path, required=True)
    parser.add_argument("--boringssl-root", type=Path, required=True)
    parser.add_argument("--icu-root", type=Path, required=True)
    parser.add_argument("--perfetto-profile", type=Path, default=Path("bcr/overlay/source/native/perfetto_inputs.json"))
    parser.add_argument("--rust-profile", type=Path, default=Path("bcr/overlay/source/native/temporal_inputs.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    result = capture(json.loads(gzip.decompress(content)), args.chromium_root, args.boringssl_root, args.icu_root, json.loads(args.perfetto_profile.read_text()), json.loads(args.rust_profile.read_text()))
    result["graph_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

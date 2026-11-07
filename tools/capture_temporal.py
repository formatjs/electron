# SPDX-License-Identifier: MIT
"""Capture Electron's Temporal/base/fontations Rust closures and original bridges."""

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
import shlex
import tomllib

ROOT = "//third_party/rust/temporal_capi/v0_1:lib"
VENDOR = "third_party/rust/chromium_crates_io/vendor/"
ALLOCATOR = "//build/rust/allocator:"
HOST = "(//build/toolchain/linux:clang_x64_for_rust_host_build_tools)"
BASE_ROOTS = ["//base:rust_logger", "//third_party/rust/serde_json_lenient/v0_2/wrapper:wrapper", "//third_party/rust/cxxbridge_cmd/v1:cxxbridge" + HOST]
NATIVE_CPP = {
    label: "@electron_base_sources//:target_" + hashlib.sha256(label.encode()).hexdigest()[:16]
    for label in [
        "//base:debugging_buildflags", "//base:tracing_buildflags", "//build:chromeos_buildflags",
        "//build/rust:cxx_cppdeps", "//base:rust_logger_cxx_generated",
        "//third_party/rust/serde_json_lenient/v0_2/wrapper:wrapper_cxx_generated",
        "//third_party/rust/serde_json_lenient/v0_2/wrapper:wrapper_functions",
    ]
}
NATIVE_CPP["//base/allocator/partition_allocator:raw_ptr"] = "@electron_partition_alloc_sources//:raw_ptr"
SEVERITY = "//base:logging_log_severity_bindgen"
SKIA_ROOTS = ["//skia:bridge_rust_side", "//skia:rust_png_ffi"]
SKIA_CPP = {label: "@electron_skia_sources//:target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in ["//skia:bridge_rust_side_cxx_generated", "//skia:path_bridge", "//skia:rust_png_ffi_cpp", "//skia:rust_png_ffi_cxx_generated"]}
FONT_ROOT = "//third_party/fontconfig:fontconfig_fontations_ffi"
FONT_BINDINGS = {"//third_party/fontconfig:" + name for name in ("fcint_h_bindgen", "fontconfig_h_bindgen")}


def name(label):
    return "crate_" + hashlib.sha256(label.encode()).hexdigest()[:16]


def capture(graph, source, fontconfig=None, skia=None):
    targets = graph["targets"]
    native_cpp = dict(NATIVE_CPP)
    if skia:
        native_cpp.update(SKIA_CPP)
    if fontconfig:
        config_source = (source / "third_party/fontconfig/BUILD.gn").read_bytes()
        config = re.search(r'config\("bindgen_config"\) \{(.*?)\n  \}', config_source.decode(), re.S)
        if not config or re.findall(r'"([^"\n]+)"', config[1]) != ["include", "BINDGEN_IGNORE_VISIBILITY=1", "FC_NO_MT=1", "FLEXIBLE_ARRAY_MEMBER=1"]:
            raise ValueError("Unexpected original Fontconfig bindgen config")
    selected, scripts, ffi, visited, provided = {}, {}, {}, set(), set()

    def value(target, key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    def infrastructure(label):
        return label.startswith(("//build/rust/std:", "//buildtools/third_party/libc++:", "//build/modules/", "//build/config:executable_deps", "//build/rust/gni_impl:rustc_print_cfg"))

    def visit(label):
        if label in visited:
            return
        visited.add(label)
        if infrastructure(label):
            provided.add(label)
            return
        if label in native_cpp:
            return
        target = targets[label]
        bare = label.split("(")[0]
        if bare in FONT_BINDINGS:
            selected[label] = target
            ffi[label] = target
            for dep in target.get("deps", []):
                if dep in FONT_BINDINGS:
                    visit(dep)
            return
        if bare in (ALLOCATOR + "allocator_impls_ffi", ALLOCATOR + "alloc_error_handler_impl_ffi", SEVERITY):
            selected[label] = target
            ffi[label] = target
            return
        kind = target["type"]
        if kind in ("rust_library", "rust_proc_macro") or kind == "executable" and target.get("crate_root"):
            selected[label] = target
        elif kind == "action" and target.get("script") == "//build/rust/gni_impl/run_build_script.py":
            binaries = [dep for dep in target["deps"] if targets[dep].get("crate_root")]
            if len(binaries) != 1:
                raise ValueError("Unexpected Rust build-script producer")
            scripts[label] = binaries[0]
        elif kind == "action" and target.get("script") == "//build/rust/gni_impl/write_rustflags.py":
            return
        elif kind != "group":
            raise ValueError("Untranslated Temporal dependency: " + label)
        for dep in target.get("deps", []):
            visit(dep)

    for root in [ROOT] + BASE_ROOTS + ([FONT_ROOT] if fontconfig else []) + (SKIA_ROOTS if skia else []):
        visit(root)
    root_files = {"LICENSE", "build/build_config.h", "build/buildflag.h", "build/rust/bindings.rs"}
    packages, crates, cpp, bindings = {}, {}, {}, {}
    script_binaries = set(scripts.values())
    labels_by_name = {name(label): label for label in selected}
    if len(labels_by_name) != len(selected):
        raise ValueError("Rust target name collision")
    generated_flags = {p for label in scripts for p in targets[label]["outputs"] if p.endswith("/cargo_flags.rs")}

    def resolve(label):
        if infrastructure(label):
            return None
        if label in native_cpp:
            return native_cpp[label]
        if label in selected:
            return name(label)
        if label in scripts:
            return name(scripts[label])
        target = targets[label]
        if target.get("script") == "//build/rust/gni_impl/write_rustflags.py":
            return None
        if target["type"] == "group":
            deps = [resolved for dep in target.get("deps", []) if (resolved := resolve(dep))]
            if len(deps) == 1:
                return deps[0]
        raise ValueError("Unmapped Temporal Rust dependency: " + label)

    def checked_file(path):
        owner, relative = source, path
        if fontconfig and path.startswith("third_party/fontconfig/src/"):
            owner, relative = fontconfig, path.removeprefix("third_party/fontconfig/src/")
        if skia and path.startswith("third_party/skia/"):
            owner, relative = skia, path.removeprefix("third_party/skia/")
        candidate = owner / relative
        if not candidate.is_file() or not candidate.resolve().is_relative_to(owner.resolve()):
            raise ValueError("Missing or escaping pinned Rust input: " + path)
        return path

    def rust_options(target):
        flags = value(target, "rustflags")
        features, retained, omitted = [], [], []
        edition = None
        index = 0
        while index < len(flags):
            flag = flags[index]
            if flag.startswith("--edition="):
                edition = flag.split("=", 1)[1]
            elif flag.startswith("--cfg=feature="):
                features.append(json.loads(flag.split("=", 2)[2]))
            elif flag.startswith("@../../build/"):
                path = checked_file(flag.removeprefix("@../../"))
                root_files.add(path)
                retained.extend(shlex.split((source / path).read_text(), comments=True))
            elif flag.startswith("@"):
                if "//out/bazel-import/" + flag[1:] not in generated_flags:
                    raise ValueError("Unmapped Rust response file: " + flag)
                omitted.append(flag)
            elif flag == "--cfg":
                retained += flags[index:index + 2]
                index += 1
            elif flag == "--extern" and flags[index + 1] == "proc_macro":
                retained += flags[index:index + 2]
                index += 1
            elif flag.startswith(("--target=", "--color=", "-Cmetadata=", "-Clinker=")):
                omitted.append(flag)
            elif flag.startswith(("--cfg=", "-Cforce-unwind-tables=", "-Crelocation-model=", "-Cembed-bitcode=", "-Clto=", "-Copt-level=", "-Cdebug-assertions", "-Cdefault-linker-libraries", "-Ctarget-feature=", "-Cpanic=", "-D", "-A", "-F", "-Zallow-features=", "-Zdep-info-omit-d-target", "-Zmacro-backtrace", "-Zremap-cwd-prefix=", "-Zexternal-clangrt", "-Zdefault-visibility=")):
                retained.append(flag)
            else:
                raise ValueError("Untranslated Rust compiler option: " + flag)
            index += 1
        if edition not in ("2015", "2018", "2021", "2024"):
            raise ValueError("Unexpected Temporal Rust edition")
        return edition, sorted(features), retained, omitted

    for label, target in sorted(selected.items()):
        if target["toolchain"] not in ("//build/toolchain/linux:clang_x64", "//build/toolchain/linux:clang_x64_for_rust_host_build_tools"):
            raise ValueError("Expected captured Temporal Linux AMD64 toolchain")
        root = checked_file(target["crate_root"][2:])
        edition, features, flags, omitted = rust_options(target)
        environment = dict(item.split("=", 1) for item in target.get("rustenv", []))
        paths = {key: environment.pop(key) for key in ("OUT_DIR", "CARGO_MANIFEST_DIR", "SDKROOT") if key in environment}
        package = "/".join(root.split("/")[:5]) if root.startswith(VENDOR) else None
        if package and package not in packages:
            inventory = sorted(checked_file(str(p.relative_to(source))) for p in (source / package).rglob("*") if p.is_file() and p.name not in ("BUILD", "BUILD.bazel", "MODULE.bazel", "WORKSPACE", "WORKSPACE.bazel"))
            manifest = tomllib.loads((source / package / "Cargo.toml").read_text())
            version = manifest["package"]["version"]
            if isinstance(version, str) and environment.get("CARGO_PKG_VERSION") != version:
                raise ValueError("Captured Rust package version differs from pinned source")
            packages[package] = inventory
        sources = []
        generated_dirs = {str(Path(output).parent) + "/" for dep in target.get("deps", []) if dep in scripts for output in targets[dep]["outputs"] if output.endswith("/cargo_flags.rs")}
        for path in target.get("sources", []):
            if path.startswith("//out/bazel-import/"):
                if not any(path.startswith(directory) for directory in generated_dirs):
                    raise ValueError("Unmapped generated Rust source")
            else:
                sources.append(checked_file(path[2:]))
        if not package:
            root_files.update(sources)
        if label in ffi:
            deps = [name(dep) for dep in target.get("deps", []) if dep in FONT_BINDINGS]
            macros, cc_deps = [], []
        else:
            deps, macros, cc_deps = [], [], []
            for dep in target.get("deps", []):
                resolved = resolve(dep)
                if resolved:
                    if resolved.startswith("@"):
                        cc_deps.append(resolved)
                        continue
                    actual = selected[labels_by_name[resolved]]
                    (macros if actual["type"] == "rust_proc_macro" else deps).append(resolved)
        kind = "cargo_build_script" if label in script_binaries else target["type"]
        if kind == "cargo_build_script":
            owners = [owner for owner in selected.values() if any(scripts.get(dep) == label for dep in owner.get("deps", []))]
            if not owners:
                raise ValueError("Rust build script has no captured owner")
            owner_features = [rust_options(owner)[1] for owner in owners]
            if any(feature_set != owner_features[0] for feature_set in owner_features):
                raise ValueError("Shared build script has different captured features")
            features = owner_features[0]
        crates[label] = {"name": name(label), "kind": kind, "crate_name": target["crate_name"], "crate_root": root, "srcs": sources, "package": package, "edition": edition, "features": features, "rustc_flags": flags, "rustc_env": environment, "rewritten_paths": paths, "deps": sorted(set(deps)), "cc_deps": sorted(set(cc_deps)), "proc_macro_deps": sorted(set(macros)), "gn_deps": target.get("deps", []), "omitted_toolchain_options": omitted, "gn_rustflags": value(target, "rustflags")}

    for label, target in ffi.items():
        suffix = HOST if label.endswith(HOST) else ""
        bare = label.removesuffix(suffix) if suffix else label
        if bare in FONT_BINDINGS:
            generator = bare + "_generator"
            action = targets[generator]
            copies = [dep for dep in target["deps"] if targets[dep]["type"] == "copy"]
            if len(copies) != 1 or action["script"] != "//build/rust/gni_impl/run_bindgen.py" or targets[copies[0]]["deps"] != [generator] or targets[copies[0]]["sources"] != action["outputs"]:
                raise ValueError("Unexpected Fontconfig binding producer")
            expected = {copies[0], "//build/rust/std:std"} | ({"//third_party/fontconfig:fontconfig_h_bindgen"} if bare.endswith(":fcint_h_bindgen") else set())
            if set(target["deps"]) != expected or len(action["sources"]) != 1:
                raise ValueError("Untranslated Fontconfig binding dependency")
            args = action["args"]
            begin, end = args.index("--bindgen-flags") + 1, args.index("--")
            header = checked_file(action["sources"][0][2:])
            bindings[label] = {"owner": "@electron_fonts_sources//:fontconfig_bindgen_headers", "header": header, "header_label": "@electron_fonts_sources//:" + header, "bindgen_flags": ["--no-layout-tests"] + ["--" + arg for arg in args[begin:end]], "clang_flags": ["-x", "c", "-std=c11", "-fparse-all-comments", "-fvisibility=default", "-DBINDGEN_IGNORE_VISIBILITY=1", "-DFC_NO_MT=1", "-DFLEXIBLE_ARRAY_MEMBER=1"], "gn_args": args, "config_source": "third_party/fontconfig/BUILD.gn", "config_source_sha256": hashlib.sha256(config_source).hexdigest()}
            continue
        if bare == SEVERITY:
            generator = SEVERITY + "_generator"
            action = targets[generator]
            copies = [dep for dep in target["deps"] if targets[dep]["type"] == "copy"]
            if len(copies) != 1 or action["script"] != "//build/rust/gni_impl/run_bindgen.py" or action["sources"] != ["//base/logging/log_severity.h"] or targets[copies[0]]["deps"] != [generator]:
                raise ValueError("Unexpected logging severity binding producer")
            args = action["args"]
            begin, end = args.index("--bindgen-flags") + 1, args.index("--")
            header = checked_file(action["sources"][0][2:])
            root_files.add(header)
            bindings[label] = {"owner": "@electron_base_sources//:severity_headers", "header": header, "header_label": "@electron_base_sources//:" + header, "bindgen_flags": ["--" + arg for arg in args[begin:end]], "gn_args": args}
            continue
        owner = bare.removesuffix("_ffi") + suffix
        generator = bare + "_generator" + suffix
        action = targets[generator]
        copies = [dep for dep in target["deps"] if targets[dep]["type"] == "copy"]
        if len(copies) != 1 or set(target["deps"]) != {owner, copies[0], "//build/rust/std:std" + suffix}:
            raise ValueError("Untranslated Rust allocator binding dependency")
        copy = targets[copies[0]]
        if copy["deps"] != [generator] or copy["sources"] != action["outputs"] or len(copy["outputs"]) != 1 or not copy["outputs"][0].endswith("/bindings.rs"):
            raise ValueError("Unexpected allocator binding copy layout")
        args = action["args"]
        if action.get("script") != "//build/rust/gni_impl/run_bindgen.py" or action["deps"] != [owner]:
            raise ValueError("Untranslated allocator bindgen producer")
        begin, end = args.index("--bindgen-flags") + 1, args.index("--")
        header = checked_file(action["sources"][0][2:])
        root_files.add(header)
        bindings[label] = {"owner": name(owner), "header": header, "bindgen_flags": ["--" + arg for arg in args[begin:end]], "gn_args": args}
        native = targets[owner]
        actual = {dep.split("(")[0] for dep in native["deps"]}
        expected = {"//buildtools/third_party/libc++:" + dep for dep in ("all_modules", "custom_headers", "libcxx_headers")}
        if bare == ALLOCATOR + "allocator_impls_ffi":
            expected |= {"//base/allocator/partition_allocator:partition_alloc", ALLOCATOR + "buildflags"}
        if actual != expected or native["type"] != "static_library":
            raise ValueError("Untranslated allocator C++ dependency")
        cpp_sources = [checked_file(path[2:]) for path in native["sources"]]
        if any(not path.endswith((".cc", ".h")) for path in cpp_sources):
            raise ValueError("Unexpected Rust allocator C++ source inventory")
        root_files.update(cpp_sources)
        retained, skipped = [], []
        for flag in value(native, "cflags") + value(native, "cflags_cc"):
            if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                skipped.append(flag)
            else:
                retained.append(flag)
        cpp[owner] = {"name": name(owner), "srcs": [path for path in cpp_sources if path.endswith(".cc")], "hdrs": [path for path in cpp_sources if path.endswith(".h")], "copts": retained, "defines": [d.replace('"', '\\"') for d in value(native, "defines")], "partition_alloc": bare == ALLOCATOR + "allocator_impls_ffi", "gn_deps": native["deps"], "omitted_toolchain_options": skipped}

    flags = targets[ALLOCATOR + "buildflags"]
    if flags["type"] != "action" or flags["deps"] != ["//build:buildflag_header_h"] or flags["script"] != "//build/write_buildflag_header.py" or flags["response_file_contents"] != ["--flags", "RUST_ALLOCATOR_USES_PARTITION_ALLOC=true", "RUST_ALLOCATOR_USES_ALIGNED_MALLOC=false"]:
        raise ValueError("Expected captured PartitionAlloc Rust bridge")
    if flags["args"] != ["--output", "build/rust/allocator/buildflags.h", "--rulename", ALLOCATOR + "buildflags", "--gen-dir", "gen", "--definitions", "{{response_file_name}}"] or flags["outputs"] != ["//out/bazel-import/gen/build/rust/allocator/buildflags.h"]:
        raise ValueError("Unexpected Rust allocator buildflag layout")
    temporal_package = VENDOR + "temporal_capi-v0_1"
    cpp_headers = [p for p in packages[temporal_package] if "/bindings/cpp/" in p and p.endswith((".h", ".hpp"))]
    if not cpp_headers:
        raise ValueError("Missing original Temporal C++ bindings")
    return {"root": name(ROOT), "base_roots": {label: name(label) for label in BASE_ROOTS}, "rust": crates, "cpp": cpp, "ffi": bindings, "packages": packages, "root_files": sorted(root_files), "cpp_headers": cpp_headers, "provided_by_toolchain": sorted(provided), "allocator_buildflags": {"output": "build/rust/allocator/buildflags.h", "rule": ALLOCATOR + "buildflags", "response": flags["response_file_contents"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--fontconfig-root", type=Path, required=True)
    parser.add_argument("--skia-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--v8-output", type=Path, required=True)
    args = parser.parse_args()
    data = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(data)), args.source_root, args.fontconfig_root, args.skia_root)
    profile["graph_sha256"] = hashlib.sha256(data).hexdigest()
    args.output.write_text(json.dumps(profile, sort_keys=True, indent=2) + "\n")
    graph = json.loads(gzip.decompress(data))
    target = graph["targets"]["//v8:v8_base_without_compiler"]
    cpp = "//v8/src/objects/js-temporal-zoneinfo64.cc"
    if cpp not in target["sources"]:
        raise ValueError("Missing captured V8 timezone provider")
    def value(key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item
    flags, omitted = [], []
    for flag in value("cflags") + value("cflags_cc"):
        if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
            omitted.append(flag)
        else:
            flags.append(flag)
    definitions = value("defines")
    if not {"V8_TEMPORAL_SUPPORT", "V8_INTL_SUPPORT", "V8_ENABLE_SANDBOX", "V8_USE_PERFETTO", "V8_TARGET_ARCH_X64", "V8_TARGET_OS_LINUX", "TEMPORAL_CAPI_VERSION_0_1"}.issubset(definitions):
        raise ValueError("Expected complete captured V8 Temporal configuration")
    provider = {"srcs": [cpp.removeprefix("//v8/")], "copts": flags, "defines": [d.replace('"', '\\"') for d in definitions], "gn_target": "//v8:v8_base_without_compiler", "gn_deps": target["deps"], "gn_defines": definitions, "omitted_toolchain_options": omitted, "graph_sha256": profile["graph_sha256"]}
    args.v8_output.write_text('"""Captured V8 timezone provider; remaining engine units are separate."""\n\nV8_TEMPORAL_PROVIDER = ' + json.dumps(provider, indent=4) + '\n')
    print("Captured", len(profile["rust"]), "Rust targets,", len(profile["cpp"]), "C++ bridge variants,", len(profile["packages"]), "vendor packages")


if __name__ == "__main__":
    main()

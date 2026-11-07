# SPDX-License-Identifier: MIT
"""Capture the complete Mojo embedder/network closure from Electron's GN import."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

BUILD = "//out/bazel-import/"
ROOT = "//mojo/core/embedder:embedder"
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
SCRIPTS = {
    "//build/util/version.py", "//build/write_buildflag_header.py",
    "//net/tools/dafsa/make_dafsa.py", "//tools/protoc_wrapper/protoc_wrapper.py",
    "//build/gn_run_binary.py", "//tools/grit/grit.py",
    "//tools/grit/stamp_grit_sources.py",
    "//tools/metrics/histograms/generate_allowlist_from_histograms_file.py",
}


def capture(graph, chromium, quiche, re2, sqlite, profiles):
    external = {}
    for name, repository in [("base", "base"), ("embedder", "embedder"), ("ipcz", "ipcz"), ("libnode", "libnode"), ("perfetto", "perfetto_native"), ("protobuf", "protobuf"), ("v8_engine", "v8_engine"), ("v8_support", "v8_support")]:
        profile = json.loads((profiles / (name + "_inputs.json")).read_text())
        external.update({label: "@electron_" + repository + "_sources//:" + target for label, target in profile.get("names", {}).items()})
        external.update(profile.get("external", {}))
        if name == "protobuf":
            external.update({label: "@electron_protobuf_sources//:" + target["name"] for label, target in profile["libraries"].items()})
    external.update({"//third_party/boringssl:boringssl": "@electron_boringssl_sources//:ssl", "//third_party/icu:icu": "@electron_icu_sources//:icu", "//third_party/abseil-cpp:absl": "@electron_protobuf_sources//:abseil", "//third_party/zlib:zlib": "@electron_v8_support_sources//:zlib", "//third_party/compiler-rt:atomic": ":atomic_runtime"})
    for revision in ("c0df0d316bd7e4ddf44e5ba094b5c5b061d94b0c", "cd7b2823a8375371f7efe6dae17837c9ab407693"):
        if revision not in (chromium / "DEPS").read_text():
            raise ValueError("Network DEPS pin changed")
    targets, seen, pending = graph["targets"], set(), [ROOT]
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}

    def value(target, key):
        item = target.get(key, [])
        return graph["pool"][item["pool"]] if isinstance(item, dict) else item

    def physical(path):
        for prefix, directory in [("net/third_party/quiche/src/", quiche), ("third_party/re2/src/", re2), ("third_party/sqlite/src/", sqlite)]:
            if path.startswith(prefix):
                return directory / path.removeprefix(prefix)
        return chromium / path

    files, headers, python, generated = set(), {}, {}, {}
    directories = ["mojo", "net", "sql", "crypto", "url", "base/version_info", "components/cbor", "components/miracle_parameter/common", "components/network_time/time_tracker", "components/performance_manager/scenario_api", "components/sqlite_proto", "components/unexportable_keys", "ui/base/glib", "third_party/re2/src", "third_party/sqlite/src/amalgamation", "net/third_party/quiche/src"]
    for directory in directories:
        root = physical(directory + "/")
        inventory = sorted(directory + "/" + path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".hpp", ".inc", ".inl"))
        if not inventory:
            raise ValueError("Missing network header inventory: " + directory)
        headers[directory] = inventory
        files.update(inventory)
    for directory in ["tools/grit", "tools/metrics/histograms", "tools/metrics/common", "tools/protoc_wrapper"]:
        python[directory] = sorted(path.relative_to(chromium).as_posix() for path in (chromium / directory).rglob("*.py") if "__pycache__" not in path.parts)
    resource_specs = sorted(path.relative_to(chromium).as_posix() for suffix in ("*.grd", "*.grdp") for path in chromium.rglob(suffix) if path.is_file())
    producers = {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "action_foreach", "executable"):
            for output in target.get("outputs", []):
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate network output")
                producers[output] = label
    tools = {output: external.get(label, ":" + names.get(label, "")) for label, target in targets.items() if target["type"] == "executable" and (label in seen or label in external) for output in target.get("outputs", [])[:1]}

    def input_file(path):
        if path.startswith(BUILD):
            if path in graph["generated_files"]:
                generated[path] = graph["generated_files"][path]
            elif path not in producers and path not in tools:
                raise ValueError("Unowned network input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Unexpected network input path")

    actions, libraries = {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 network profile")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind in ("action", "action_foreach"):
            script = target["script"]
            if script not in SCRIPTS:
                raise ValueError("Untranslated network generator: " + script)
            inputs = set(target.get("inputs", []) + [script])
            if script == "//build/util/version.py":
                inputs.add("//build/util/android_chrome_version.py")
            if script.startswith("//tools/grit/"):
                inputs.update("//" + path for path in python["tools/grit"])
                if label == "//tools/gritsettings:default_resource_ids":
                    inputs.update("//" + path for path in resource_specs)
                if label == "//net:net_resources_grit":
                    inputs.add("//net/base/dir_header.html")
            if script.startswith("//tools/metrics/"):
                inputs.update("//" + path for directory in ("tools/metrics/histograms", "tools/metrics/common") for path in python[directory])
            if script == "//tools/protoc_wrapper/protoc_wrapper.py":
                inputs.update("//" + path for path in python["tools/protoc_wrapper"])
            runs = []
            for index, source in enumerate(target.get("sources", []) if kind == "action_foreach" else [None]):
                current = inputs | ({source} if source else set(target.get("sources", [])))
                args, outputs = target.get("args", []), target["outputs"]
                if source:
                    args = [arg.replace("{{source}}", "../../" + source[2:]).replace("{{source_name_part}}", Path(source).stem) for arg in args]
                    outputs = [target["outputs"][index]]
                if any("{{" in arg and arg != "{{response_file_name}}" for arg in args):
                    raise ValueError("Untranslated network generator placeholder")
                for path in current:
                    input_file(path)
                runs.append(dict(inputs=sorted(current), outputs=outputs, args=args, tools={path: tools[path] for path in sorted(current) if path in tools}))
            record.update(script=script[2:], response=target.get("response_file_contents", []), runs=runs, outputs=target["outputs"])
            actions[label] = record
        elif kind in ("static_library", "source_set", "executable", "group"):
            sources = target.get("sources", [])
            if any(Path(path).suffix not in (".h", ".inc", ".cc", ".cpp", ".c", ".S", ".s") for path in sources):
                raise ValueError("Untranslated network source language: " + label)
            for path in sources:
                input_file(path)
            flags, omitted = {}, []
            for language, key in [("cc", "cflags_cc"), ("c", "cflags_c"), ("asm", "asmflags")]:
                flags[language] = []
                for flag in value(target, "cflags") + value(target, key):
                    if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                        omitted.append(flag)
                    else:
                        flags[language].append(flag)
            includes = []
            for path in value(target, "include_dirs"):
                if path == "//buildtools/third_party/libc++/":
                    continue
                if path.startswith(BUILD):
                    includes.append(path.removeprefix(BUILD).rstrip("/") or ".")
                elif path.startswith("//"):
                    includes.append(path[2:].rstrip("/") or ".")
                else:
                    raise ValueError("Unexpected network include root")
            libs = value(target, "libs")
            if set(libs) - {"m", "dl", "rt", "pthread", "resolv", "gio-2.0", "glib-2.0", "gmodule-2.0", "gobject-2.0", "gthread-2.0", "nspr4", "nss3", "nssutil3", "plc4", "plds4", "smime3", "$LLVM_ROOT/lib/clang/23/lib/x86_64-unknown-linux-gnu/libclang_rt.builtins.a"}:
                raise ValueError("Untranslated network library")
            record.update(srcs=[path for path in sources if path.endswith((".cc", ".cpp"))], c_srcs=[path for path in sources if path.endswith(".c")], asm_srcs=[path for path in sources if path.endswith((".S", ".s"))], generated_headers=[path for path in sources if path.startswith(BUILD) and path.endswith((".h", ".inc"))], copts=flags["cc"], c_copts=flags["c"], asm_copts=flags["asm"], defines=[item.replace('"', '\\"') for item in value(target, "defines")], includes=includes, libs=libs, gn_include_dirs=value(target, "include_dirs"), gn_ldflags=value(target, "ldflags"), omitted_toolchain_and_diagnostic_flags=sorted(set(omitted)))
            libraries[label] = record
        else:
            raise ValueError("Untranslated network target kind: " + kind)
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original network input: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return dict(root=ROOT, names=names, libraries=libraries, actions=actions, producers=producers, files=sorted(files), headers=headers, generated_files=generated, external={label: external[label] for label in sorted(used)}, toolchain_deps=sorted(TOOLCHAIN))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "quiche-root", "re2-root", "sqlite-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    result = capture(json.loads(gzip.decompress(content)), args.chromium_root, args.quiche_root, args.re2_root, args.sqlite_root, args.profiles)
    result["graph_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

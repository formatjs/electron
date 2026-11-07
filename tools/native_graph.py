# SPDX-License-Identifier: MIT
"""Shared native C/C++ capture; preserve source configuration and declared inputs."""

from pathlib import Path
import json

BUILD = "//out/bazel-import/"
DIAGNOSTIC_INPUTS = {"//build/config/unsafe_buffers_paths.txt", "//build/config/warning_suppression.txt"}


def value(graph, target, key):
    item = target.get(key, [])
    return graph["pool"][item["pool"]] if isinstance(item, dict) else item


def capture_library(graph, target, record, input_file, label, extra_libs=()):
    sources = target.get("sources", [])
    public = target.get("public", [])
    public = public if isinstance(public, list) else []
    compiler_inputs = [path for path in target.get("inputs", []) if path not in DIAGNOSTIC_INPUTS]
    if any(Path(path).suffix not in (".h", ".hh", ".hpp", ".inc", ".inl", ".cc", ".cpp", ".c", ".S", ".s", ".o") for path in sources):
        raise ValueError("Untranslated native source language: " + label)
    for path in sources + public + compiler_inputs:
        input_file(path)
    flags, omitted = {}, []
    for language, key in [("cc", "cflags_cc"), ("c", "cflags_c"), ("asm", "asmflags")]:
        flags[language] = []
        for flag in value(graph, target, "cflags") + value(graph, target, key):
            if flag in ("-Werror", "-nostdinc++") or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                omitted.append(flag)
            else:
                flags[language].append(flag)
    includes = []
    for path in value(graph, target, "include_dirs"):
        if path == "//buildtools/third_party/libc++/":
            continue
        if path.startswith(BUILD):
            includes.append(path.removeprefix(BUILD).rstrip("/") or ".")
        elif path.startswith("//"):
            includes.append(path[2:].rstrip("/") or ".")
        else:
            raise ValueError("Unexpected native include root")
    libs = value(graph, target, "libs")
    if set(libs) - set(extra_libs) - {"m", "dl", "rt", "pthread", "resolv", "xcb", "xkbcommon", "uuid", "expat", "gio-2.0", "glib-2.0", "gmodule-2.0", "gobject-2.0", "gthread-2.0", "nspr4", "nss3", "nssutil3", "plc4", "plds4", "smime3", "$LLVM_ROOT/lib/clang/23/lib/x86_64-unknown-linux-gnu/libclang_rt.builtins.a"}:
        raise ValueError("Untranslated native library")
    record.update(srcs=[path for path in sources if path.endswith((".cc", ".cpp", ".o"))], c_srcs=[path for path in sources if path.endswith(".c")], asm_srcs=[path for path in sources if path.endswith((".S", ".s"))], generated_headers=[path for path in sources if path.startswith(BUILD) and path.endswith((".h", ".hh", ".hpp", ".inc"))], copts=flags["cc"], c_copts=flags["c"], asm_copts=flags["asm"], defines=[item.replace('"', '\\"') for item in value(graph, target, "defines")], includes=includes, libs=libs, gn_include_dirs=value(graph, target, "include_dirs"), gn_ldflags=value(graph, target, "ldflags"), omitted_toolchain_and_diagnostic_flags=sorted(set(omitted)))
    record["public_headers"] = public
    record["source_headers"] = [path for path in sources if path.endswith((".h", ".hh", ".hpp", ".inc", ".inl"))]
    record["compiler_inputs"] = compiler_inputs
    record["omitted_diagnostic_inputs"] = [path for path in target.get("inputs", []) if path in DIAGNOSTIC_INPUTS]
    return record


def load_profiles(directory, profiles):
    """Share owned target/file identities across captured native closures."""
    external, shared = {}, {}
    for name, repository in profiles:
        profile = json.loads((directory / (name + "_inputs.json")).read_text())
        owner = "@electron_" + repository + "_sources//:"
        external.update({label: owner + target for label, target in profile.get("names", {}).items()})
        external.update({label: owner + target[1:] if target.startswith(":") else target for label, target in profile.get("external", {}).items()})
        if name == "protobuf":
            external.update({label: owner + target["name"] for label, target in profile["libraries"].items()})
        for path in profile.get("files", []):
            shared.setdefault("//" + path, owner + path)
        for path in profile.get("producers", {}):
            shared.setdefault(path, owner + (path[2:] if path in profile.get("generated_files", {}) else path.removeprefix(BUILD)))
    return external, shared

# SPDX-License-Identifier: MIT
"""Shared native C/C++ capture; preserve source configuration and declared inputs."""

from pathlib import Path
import json
from capture_target import builtins_archive, target_toolchain

BUILD = "//out/bazel-import/"
DIAGNOSTIC_INPUTS = {"//build/config/unsafe_buffers_paths.txt", "//build/config/warning_suppression.txt"}
LINUX_ARCHITECTURES = {target_toolchain(architecture): architecture for architecture in ('x64', 'arm64')}
LINUX_ARCHITECTURES['//build/toolchain/linux:clang_x64_for_rust_host_build_tools'] = 'x64'


def pack_profile(profile):
    strings, indices = [], {}

    def pack(value):
        if isinstance(value, dict):
            if "_strings" in value or "_string_pool" in value:
                raise ValueError("Reserved native profile key")
            return {key: pack(item) for key, item in value.items()}
        if isinstance(value, list):
            if value and all(isinstance(item, str) for item in value):
                ids = []
                for item in value:
                    if item not in indices:
                        indices[item] = len(strings)
                        strings.append(item)
                    ids.append(indices[item])
                return {"_strings": ids}
            return [pack(item) for item in value]
        return value

    result = pack(profile)
    result["_string_pool"] = strings
    return result


def unpack_profile(profile):
    if "_string_pool" not in profile:
        return profile
    pool = profile.pop("_string_pool")
    if not isinstance(pool, list) or not all(isinstance(item, str) for item in pool):
        raise ValueError("Invalid native profile string pool")

    def unpack(value):
        if isinstance(value, dict):
            if "_strings" in value:
                if set(value) != {"_strings"} or not isinstance(value["_strings"], list):
                    raise ValueError("Invalid native profile string reference")
                if not all(type(index) is int and 0 <= index < len(pool) for index in value["_strings"]):
                    raise ValueError("Invalid native profile string index")
                return [pool[index] for index in value["_strings"]]
            return {key: unpack(item) for key, item in value.items()}
        if isinstance(value, list):
            return [unpack(item) for item in value]
        return value

    return unpack(profile)


def value(graph, target, key):
    item = target.get(key, [])
    return graph["pool"][item["pool"]] if isinstance(item, dict) else item


def capture_library(graph, target, record, input_file, label, extra_libs=()):
    architecture = LINUX_ARCHITECTURES.get(target.get('toolchain'))
    resources = [path for path in target.get("sources", []) if path.endswith(".grd") or (path.endswith(".rc") and architecture is not None)]
    # GN skips Objective-C sources when the Linux toolchain has no objc tools.
    ignored = [path for path in target.get("sources", []) if architecture is not None and Path(path).suffix in (".m", ".mm")]
    sources = [path for path in target.get("sources", []) if path not in resources and path not in ignored]
    if ignored:
        record["gn_uncompiled_sources"] = ignored
        for path in ignored:
            input_file(path)
    if resources:
        record["resource_sources"] = resources
    for path in resources:
        input_file(path)
    public = target.get("public", [])
    public = public if isinstance(public, list) else []
    compiler_inputs = [path for path in target.get("inputs", []) if path not in DIAGNOSTIC_INPUTS]
    if any(Path(path).suffix not in (".h", ".hh", ".hpp", ".hxx", ".inc", ".inl", ".cc", ".cpp", ".cxx", ".c", ".S", ".s", ".o") for path in sources):
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
    builtins = {builtins_archive(architecture)} if architecture is not None else set()
    if set(libs) - set(extra_libs) - builtins - {"m", "dl", "rt", "pthread", "resolv", "xcb", "xkbcommon", "uuid", "expat", "gio-2.0", "glib-2.0", "gmodule-2.0", "gobject-2.0", "gthread-2.0", "nspr4", "nss3", "nssutil3", "plc4", "plds4", "smime3"}:
        raise ValueError("Untranslated native library")
    record.update(srcs=[path for path in sources if path.endswith((".cc", ".cpp", ".cxx", ".o"))], c_srcs=[path for path in sources if path.endswith(".c")], asm_srcs=[path for path in sources if path.endswith((".S", ".s"))], generated_headers=[path for path in sources if path.startswith(BUILD) and path.endswith((".h", ".hh", ".hpp", ".hxx", ".inc"))], copts=flags["cc"], c_copts=flags["c"], asm_copts=flags["asm"], defines=[item.replace('"', '\\"').replace(" ", "\\ ").replace("\t", "\\\t") for item in value(graph, target, "defines")], includes=includes, libs=libs, gn_include_dirs=value(graph, target, "include_dirs"), gn_ldflags=value(graph, target, "ldflags"), omitted_toolchain_and_diagnostic_flags=sorted(set(omitted)))
    record["public_headers"] = public
    record["source_headers"] = [path for path in sources if path.endswith((".h", ".hh", ".hpp", ".hxx", ".inc", ".inl"))]
    record["compiler_inputs"] = compiler_inputs
    record["omitted_diagnostic_inputs"] = [path for path in target.get("inputs", []) if path in DIAGNOSTIC_INPUTS]
    return record


def load_profiles(directory, profiles):
    """Share owned target/file identities across captured native closures."""
    external, shared = {}, {}
    for name, repository in profiles:
        profile = unpack_profile(json.loads((directory / (name + "_inputs.json")).read_text()))
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

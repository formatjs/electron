# SPDX-License-Identifier: MIT
"""Capture complete matching Skia/Dawn native closure and original generators."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from native_graph import BUILD, capture_library
from capture_temporal import SKIA_CPP

ROOT = "//skia:skia"
CXX = "//third_party/rust/cxxbridge_cmd/v1:cxxbridge(//build/toolchain/linux:clang_x64_for_rust_host_build_tools)"
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
PINS = {"skia": "f4ed99d2443962782cf5f8b4dd27179f131e7cbe", "dawn": "cee9cb0d67e749bf42f5e90cb3b8a6f525dbb920", "vulkan": "a4f8ada9f4f97c45b8c89c57997be9cebaae65d2"}
SCRIPTS = {"//" + path for path in ["build/write_buildflag_header.py", "gpu/config/build_workaround_header.py", "third_party/dawn/generator/dawn_json_generator.py", "third_party/dawn/generator/dawn_gpu_info_generator.py", "third_party/dawn/generator/dawn_version_generator.py", "third_party/dawn/generator/extract_json.py", "third_party/rust/cxx/chromium_integration/run_cxxbridge.py"]}


def capture(graph, digest, chromium, skia, dawn, vulkan, profiles):
    external, shared = {}, {}
    for name, repository in [("base", "base"), ("embedder", "embedder"), ("ipcz", "ipcz"), ("libnode", "libnode"), ("perfetto", "perfetto_native"), ("protobuf", "protobuf"), ("v8_engine", "v8_engine"), ("v8_support", "v8_support"), ("network", "network"), ("mojo", "mojo"), ("fonts", "fonts"), ("codecs", "codecs")]:
        profile = json.loads((profiles / (name + "_inputs.json")).read_text())
        owner = "@electron_" + repository + "_sources//:"
        external.update({label: owner + target for label, target in profile.get("names", {}).items()})
        external.update({label: owner + target[1:] if target.startswith(":") else target for label, target in profile.get("external", {}).items()})
        if name == "protobuf":
            external.update({label: owner + target["name"] for label, target in profile["libraries"].items()})
        for path in profile.get("files", []):
            shared.setdefault("//" + path, owner + path)
        for path in profile.get("producers", {}):
            shared.setdefault(path, owner + path.removeprefix(BUILD))
    rust = json.loads((profiles / "temporal_inputs.json").read_text())
    external.update({label: "@electron_rust_sources//:" + crate["name"] for label, crate in rust["rust"].items()})
    if rust["graph_sha256"] != digest or any(rev not in (chromium / "DEPS").read_text() for rev in PINS.values()):
        raise ValueError("Expected matching Skia/Dawn source and Rust graph")
    targets, seen, pending = graph["targets"], set(), [ROOT] + list(SKIA_CPP)
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        if not label.startswith(("//skia:", "//third_party/dawn/", "//third_party/vulkan-headers/src:", "//gpu/config:", "//ui/base:", "//third_party/expat:")):
            raise ValueError("Untranslated Skia dependency: " + label)
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}
    roots = {"third_party/skia": skia, "third_party/dawn": dawn, "third_party/vulkan-headers/src": vulkan}

    def physical(path):
        for prefix, root in roots.items():
            if path.startswith(prefix + "/"):
                return root / path[len(prefix) + 1:]
        return chromium / path

    files, generated, headers, textual, used_shared = set(), {}, {}, {}, set()
    source_metadata = {"gpu/webgpu/DAWN_VERSION": PINS["dawn"]}
    producers = {output: label for label in sorted(seen) if targets[label]["type"] in ("action", "action_foreach") for output in targets[label]["outputs"]}
    tools = {BUILD + "clang_x64_for_rust_host_build_tools/cxxbridge": "@electron_rust_sources//:cxxbridge"}

    def input_file(path):
        if path.removeprefix("//") in source_metadata:
            return
        if path in shared:
            used_shared.add(path)
            return
        if path.startswith(BUILD):
            if path in generated:
                return
            if path in graph["generated_files"]:
                generated[path] = graph["generated_files"][path]
            elif path not in producers:
                raise ValueError("Unowned Skia generator input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Invalid Skia source path")

    for directory in ["skia", "gpu/config", "ui/base", "third_party/skia", "third_party/dawn", "third_party/vulkan-headers/src"]:
        inventory = set()
        if directory == "third_party/dawn":
            directories = [directory + "/" + suffix for suffix in ("include", "src/dawn/common", "src/dawn/partition_alloc", "src/utils")]
        else:
            directories = [directory]
        for prefix in directories:
            root = physical(prefix + "/")
            inventory.update(prefix + "/" + path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".hpp", ".inc", ".inl", ".sksl"))
        headers[directory] = sorted(path for path in inventory if not path.endswith(".sksl"))
        textual[directory] = sorted(path for path in inventory if path.endswith(".sksl"))
        for path in inventory:
            input_file("//" + path)
    python_inputs = set()
    for directory in ("third_party/jinja2", "third_party/markupsafe"):
        python_inputs.update("//" + path.relative_to(chromium).as_posix() for path in (chromium / directory).rglob("*.py") if "__pycache__" not in path.parts)
    dawn_inputs = {"//third_party/dawn/generator/" + path.relative_to(dawn / "generator").as_posix() for path in (dawn / "generator").rglob("*") if path.is_file() and path.suffix not in (".pyc",) and "__pycache__" not in path.parts}
    actions, libraries, metadata_derivations = {}, {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 Skia profile")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind in ("action", "action_foreach"):
            script = target["script"]
            if script not in SCRIPTS:
                raise ValueError("Untranslated original Skia generator")
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [script])
            args = list(target.get("args", []))
            tool_inputs = {}
            if kind == "action_foreach":
                if script != "//third_party/rust/cxx/chromium_integration/run_cxxbridge.py" or len(target["sources"]) != 1:
                    raise ValueError("Expected single original Rust CXX bridge")
                source = target["sources"][0][2:]
                for before, after in {"{{source_gen_dir}}": "gen/" + str(Path(source).parent), "{{source_file_part}}": Path(source).name, "{{source}}": "../../" + source}.items():
                    args = [arg.replace(before, after) for arg in args]
                inputs.update(["//build/action_helpers.py", "//build/gn_helpers.py"])
                tool_inputs = tools
            args = [arg.replace("$SOURCE_ROOT/out/bazel-import/", "") for arg in args]
            if script.startswith("//third_party/dawn/generator/"):
                inputs.update(dawn_inputs | python_inputs)
            if "--expected-outputs-file" in args:
                path = BUILD + args[args.index("--expected-outputs-file") + 1]
                extractor_label = label.removesuffix("__json_tarball")
                extractor = targets[extractor_label]
                if extractor["script"] != "//third_party/dawn/generator/extract_json.py" or extractor["inputs"] != target["outputs"]:
                    raise ValueError("Unexpected Dawn output metadata owner")
                prefix = BUILD + extractor["args"][1] + "/"
                if any(not output.startswith(prefix) for output in extractor["outputs"]):
                    raise ValueError("Invalid Dawn expected output path")
                declaration = (dawn / "generator/generator_lib.gni").read_bytes()
                if b"write_file(_expected_outputs_file, invoker.outputs)" not in declaration:
                    raise ValueError("Original Dawn metadata declaration changed")
                generated[path] = "\n".join(output[len(prefix):] for output in extractor["outputs"]) + "\n"
                metadata_derivations[path] = {"extractor": extractor_label, "source": "third_party/dawn/generator/generator_lib.gni", "source_sha256": hashlib.sha256(declaration).hexdigest()}
                inputs.add(path)
            for arg in args:
                if arg.startswith("../../") and (physical(arg[6:]).is_file() or arg[6:] in source_metadata):
                    inputs.add("//" + arg[6:])
                elif BUILD + arg in graph["generated_files"]:
                    inputs.add(BUILD + arg)
            if any("{{" in arg and arg != "{{response_file_name}}" for arg in args):
                raise ValueError("Untranslated Skia generator placeholder")
            inputs.difference_update(tools)
            for path in inputs:
                input_file(path)
            record.update(script=script[2:], inputs=sorted(inputs), args=args, outputs=target["outputs"], response=target.get("response_file_contents", []), tools=tool_inputs)
            actions[label] = record
        elif kind in ("group", "source_set", "static_library"):
            libraries[label] = capture_library(graph, target, record, input_file, label)
        else:
            raise ValueError("Untranslated Skia target kind: " + kind)
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original Skia input: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return dict(root=ROOT, graph_sha256=digest, source_revisions=PINS, names=names, libraries=libraries, actions=actions, producers=producers, headers=headers, textual_headers=textual, files=sorted(files), external_files={path: shared[path] for path in sorted(used_shared)}, external={label: external[label] for label in sorted(used)}, generated_files=generated, source_metadata=source_metadata, metadata_derivations=metadata_derivations, toolchain_deps=sorted(TOOLCHAIN))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "skia-root", "dawn-root", "vulkan-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, args.skia_root, args.dawn_root, args.vulkan_root, args.profiles)
    args.output.write_text(json.dumps(profile, indent=2) + "\n")


if __name__ == "__main__":
    main()

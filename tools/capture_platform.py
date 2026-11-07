# SPDX-License-Identifier: MIT
"""Capture native Linux graphics, GPU command buffers and original generators."""

import argparse
import ast
import gzip
import hashlib
import json
import os
import posixpath
import re
from pathlib import Path

from capture_mojo import SCRIPTS as MOJO_SCRIPTS
from native_graph import BUILD, capture_library, load_profiles

ROOTS = ["//ui/ozone:ozone", "//ui/gl:gl", "//gpu/command_buffer/client:gles2_implementation", "//gpu/command_buffer/service:gles2", "//components/viz/common:common"]
SOURCE_PREFIXES = ["third_party/libyuv", "third_party/angle", "third_party/dawn", "third_party/swiftshader", "third_party/spirv-tools/src", "third_party/spirv-headers/src", "third_party/vulkan-loader/src", "third_party/vulkan-tools/src", "third_party/vulkan-utility-libraries/src", "third_party/vulkan-headers/src", "third_party/vulkan_memory_allocator", "third_party/wayland/src", "third_party/wayland-protocols/src", "third_party/wayland-protocols/kde"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
SDK_LIBS = {"ffi_pic", "X11", "Xi", "Xext", "pci", "gbm", "dbus-1", "udev", "cairo", "harfbuzz", "pango-1.0", "pangocairo-1.0", "atk-1.0", "atk-bridge-2.0"}
SCRIPTS = MOJO_SCRIPTS | {"//" + name for name in (
    "build/write_buildflag_header.py", "build/gn_run_binary.py",
    "gpu/config/process_json.py", "tools/protoc_wrapper/protoc_wrapper.py",
    "third_party/wayland/wayland_scanner_wrapper.py",
    "third_party/spirv-tools/src/utils/generate_language_headers.py",
    "third_party/spirv-tools/src/utils/generate_registry_tables.py",
    "third_party/spirv-tools/src/utils/ggt.py",
    "third_party/swiftshader/third_party/SPIRV-Tools/utils/generate_language_headers.py",
    "third_party/swiftshader/third_party/SPIRV-Tools/utils/generate_registry_tables.py",
    "third_party/swiftshader/third_party/SPIRV-Tools/utils/ggt.py",
    "third_party/swiftshader/src/Vulkan/write_icd_json.py",
    "third_party/dawn/generator/extract_json.py",
    "third_party/dawn/generator/opengl_loader_generator.py",
    "third_party/dawn/generator/dawn_json_generator.py",
    "third_party/vulkan-tools/src/scripts/gn/generate_vulkan_icd_json.py",
    "net/tools/dafsa/make_dafsa.py", "third_party/angle/src/commit_id.py",
    "third_party/angle/src/program_serialize_data_version.py",
    "ui/ozone/generate_constructor_list.py", "ui/ozone/generate_ozone_platform_list.py",
)}


def source_files(root):
    for directory, children, filenames in os.walk(root, followlinks=True):
        children[:] = sorted(name for name in children if name not in (".git", "__pycache__"))
        for name in sorted(filenames):
            yield Path(directory) / name


def source_revisions(chromium):
    def read_deps(path):
        tree = ast.parse(path.read_text())
        assignments = {name.id: node.value for node in tree.body if isinstance(node, ast.Assign) for name in node.targets if isinstance(name, ast.Name)}
        variables = {key.value: value for key, value in zip(assignments["vars"].keys, assignments["vars"].values) if isinstance(key, ast.Constant)}
        entries = {key.value: value for key, value in zip(assignments["deps"].keys, assignments["deps"].values) if isinstance(key, ast.Constant)}
        return variables, entries

    variables, entries = read_deps(chromium / "DEPS")

    def text(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return text(node.left) + text(node.right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Var" and len(node.args) == 1 and not node.keywords:
            return text(variables[ast.literal_eval(node.args[0])])
        raise ValueError("Unsupported source pin expression")

    records = {}
    def record(prefix, node):
        if isinstance(node, ast.Dict):
            node = next(value for key, value in zip(node.keys, node.values) if isinstance(key, ast.Constant) and key.value == "url")
        url = text(node).replace("{chromium_git}", text(variables["chromium_git"]))
        remote, commit = url.rsplit("@", 1)
        if not remote.startswith("https://") or not re.fullmatch("[0-9a-f]{40}", commit):
            raise ValueError("Invalid exact platform source revision")
        records[prefix] = dict(remote=remote, commit=commit)
    for prefix in SOURCE_PREFIXES:
        record(prefix, entries["src/" + prefix])
    variables, entries = read_deps(chromium / "third_party/dawn/DEPS")
    for prefix in ["third_party/khronos/EGL-Registry", "third_party/khronos/OpenGL-Registry"]:
        record("third_party/dawn/" + prefix, entries[prefix])
    return records


def capture(graph, digest, chromium, source_roots, profiles):
    revisions = source_revisions(chromium)
    previous = [("base", "base"), ("embedder", "embedder"), ("ipcz", "ipcz"), ("libnode", "libnode"), ("perfetto", "perfetto_native"), ("protobuf", "protobuf"), ("v8_engine", "v8_engine"), ("v8_support", "v8_support"), ("network", "network"), ("mojo", "mojo"), ("fonts", "fonts"), ("codecs", "codecs"), ("skia", "skia"), ("gfx", "gfx"), ("display", "display"), ("events", "events"), ("ui", "ui")]
    external, shared = load_profiles(profiles, previous)
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}

    def physical(path):
        for prefix, root in sorted(source_roots.items(), key=lambda item: -len(item[0])):
            if path == prefix or path.startswith(prefix + "/"):
                return root / path[len(prefix):].lstrip("/")
        return chromium / path

    hook_label = "//gpu/webgpu:checkout_lastchange_dawn"
    hook_name = "checkout_lastchange_dawn"
    hook_outputs = [BUILD + "src/gpu/webgpu/" + name for name in ["DAWN_VERSION", "dawn_commit_hash.h"]]
    source_aliases = {"//gpu/webgpu/" + path.rsplit("/", 1)[-1]: path for path in hook_outputs}
    dawn = revisions["third_party/dawn"]["commit"]
    if dawn != "cee9cb0d67e749bf42f5e90cb3b8a6f525dbb920":
        raise ValueError("Update pinned Dawn checkout-hook commit metadata")
    tree = ast.parse((chromium / "DEPS").read_text())
    hook_list = next(node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(name, ast.Name) and name.id == "hooks" for name in node.targets))
    hook = next(node for node in hook_list.elts if isinstance(node, ast.Dict) and any(isinstance(key, ast.Constant) and key.value == "name" and isinstance(value, ast.Constant) and value.value == "lastchange_dawn" for key, value in zip(node.keys, node.values)))
    original_command = ast.literal_eval(next(value for key, value in zip(hook.keys, hook.values) if isinstance(key, ast.Constant) and key.value == "action"))
    expected_command = ["python3", "src/build/util/lastchange.py", "-m", "DAWN_COMMIT_HASH", "-s", "src/third_party/dawn", "--revision", "src/gpu/webgpu/DAWN_VERSION", "--header", "src/gpu/webgpu/dawn_commit_hash.h"]
    if original_command != expected_command:
        raise ValueError("Original Dawn checkout hook changed")
    names[hook_label] = hook_name
    files, generated, headers, used_shared = set(), {}, {}, set()
    literal_metadata = {}
    producers = {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "action_foreach", "generated_file"):
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate platform output")
                producers[output] = label
    producers.update({path: hook_label for path in hook_outputs})
    tools = {output: label for label, target in targets.items() if target["type"] == "executable" and (label in seen or label in external) for output in target.get("outputs", [])[:1]}
    execution_closure, pending = set(), [label for label in seen if targets[label]["type"] == "executable"]
    while pending:
        label = pending.pop()
        if label in execution_closure or label not in seen:
            continue
        execution_closure.add(label)
        pending.extend(targets[label].get("deps", []))

    def input_file(path):
        if path in source_aliases:
            return
        if path in tools:
            return
        if path in generated:
            return
        if path in shared:
            used_shared.add(path)
        elif path.startswith(BUILD):
            if path in graph["generated_files"]:
                generated[path] = graph["generated_files"][path]
            elif path not in producers:
                raise ValueError("Unowned platform input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Invalid platform source path")

    directories = ["third_party/libyuv", "gpu", "components/viz/common", "third_party/khronos", "ui", "dbus", "components/dbus", "components/url_formatter", "components/headless", "services/service_manager/public", "third_party/angle", "third_party/dawn", "third_party/swiftshader", "third_party/spirv-tools/src", "third_party/spirv-headers/src", "third_party/vulkan-loader/src", "third_party/vulkan-tools/src", "third_party/vulkan-utility-libraries/src", "third_party/vulkan-headers/src", "third_party/wayland/src", "third_party/wayland/include"]
    for directory in directories:
        root = physical(directory)
        inventory = sorted(directory + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.is_file() and path.suffix in (".h", ".hh", ".hpp", ".hpp11", ".inc", ".inl", ".def", ".gen"))
        if not inventory:
            raise ValueError("Missing original platform header inventory: " + directory)
        headers[directory] = inventory
        for path in inventory:
            input_file("//" + path)

    headers["khronos_exports"] = ["gpu/command_buffer/client/gles2_c_lib_export.h"]
    for path in headers["khronos_exports"]:
        input_file("//" + path)

    def dependency_inputs(label):
        paths, visited, pending = set(), set(), list(targets[label].get("deps", []))
        while pending:
            dependency = pending.pop()
            if dependency in visited:
                continue
            visited.add(dependency)
            target = targets[dependency]
            if target["type"] in ("action", "action_foreach", "copy", "generated_file"):
                paths.update(target.get("outputs", []))
                paths.update(target.get("inputs", []))
                paths.update(target.get("sources", []))
            elif target["type"] != "group":
                continue
            pending.extend(target.get("deps", []))
        return paths

    actions, libraries, metadata = {}, {}, {}
    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 platform profile")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind in ("action", "action_foreach"):
            if target["script"] not in SCRIPTS:
                raise ValueError("Untranslated platform generator: " + target["script"])
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [target["script"]]) | dependency_inputs(label)
            script_parent = physical(target["script"][2:]).parent
            for path in script_parent.glob("*.py"):
                inputs.add(target["script"].rsplit("/", 1)[0] + "/" + path.name)
            args = [arg.replace("$SOURCE_ROOT/out/bazel-import/", "") for arg in target.get("args", [])]
            if "--jinja2-path" in args:
                package = args[args.index("--jinja2-path") + 1]
                if package != "../../third_party/jinja2":
                    raise ValueError("Untranslated platform Jinja package path")
                for directory in ("third_party/jinja2", "third_party/markupsafe"):
                    root = physical(directory)
                    inputs.update("//" + directory + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.suffix == ".py")
            if "--template-dir" in args:
                directory = args[args.index("--template-dir") + 1]
                if directory != "../../third_party/dawn/generator/templates":
                    raise ValueError("Untranslated platform template path")
                root = physical(directory[6:])
                inputs.update("//" + directory[6:] + "/" + path.relative_to(root).as_posix() for path in source_files(root) if path.is_file())
            if "--expected-outputs-file" in args:
                extraction_label = label.removesuffix("__json_tarball")
                extraction = targets[extraction_label]
                if not label.endswith("__json_tarball") or extraction.get("script") != "//third_party/dawn/generator/extract_json.py" or extraction["args"][0] != args[args.index("--output-json-tarball") + 1]:
                    raise ValueError("Untranslated original Dawn output declaration")
                prefix = BUILD + extraction["args"][1] + "/"
                if any(not output.startswith(prefix) for output in extraction["outputs"]):
                    raise ValueError("Original Dawn output escapes generation root")
                path = BUILD + args[args.index("--expected-outputs-file") + 1]
                outputs = [output.removeprefix(prefix) for output in extraction["outputs"]]
                generated[path] = "\n".join(outputs) + "\n"
                literal_metadata[path] = dict(source="third_party/dawn/generator/generator_lib.gni", target=extraction_label, outputs=outputs)
                inputs.add(path)
            if target["script"] == "//mojo/public/tools/bindings/mojom_bindings_generator.py":
                template = {"c++": "cpp_templates.zip", "typescript": "ts_templates.zip", "javascript": "js_templates.zip"}[args[args.index("-g") + 1]]
                inputs.add(BUILD + args[args.index("--bytecode_path") + 1] + "/" + template)
            for arg in args:
                if arg.startswith("../../") and physical(arg[6:]).is_file():
                    inputs.add("//" + arg[6:])
                elif BUILD + arg in graph["generated_files"]:
                    inputs.add(BUILD + arg)
            runs = []
            if kind == "action_foreach":
                for source in target["sources"]:
                    substitutions = {"{{source}}": "../../" + source[2:], "{{source_name_part}}": Path(source).stem}
                    expanded = args
                    for placeholder, value in substitutions.items():
                        expanded = [arg.replace(placeholder, value) for arg in expanded]
                    runs.append(dict(args=expanded, outputs=[BUILD + path for path in target["source_outputs"][source]]))
                if sorted(path for run in runs for path in run["outputs"]) != sorted(target["outputs"]):
                    raise ValueError("Platform foreach output expansion changed")
            else:
                runs.append(dict(args=args, outputs=target["outputs"]))
            if any("{{" in arg.replace("{{response_file_name}}", "") for run in runs for arg in run["args"]):
                raise ValueError("Untranslated platform generator placeholder")
            for path in sorted(inputs):
                input_file(path)
            record.update(script=target["script"][2:], inputs=sorted(inputs - tools.keys()), tools={path: tools[path] for path in sorted(inputs) if path in tools}, outputs=target["outputs"], runs=runs, response=target.get("response_file_contents", []))
            record["environment"] = {"ANGLE_UPSTREAM_HASH": revisions["third_party/angle"]["commit"][:12]} if target["script"] == "//third_party/angle/src/commit_id.py" else {}
            actions[label] = record
        elif kind == "generated_file":
            for path in target["outputs"]:
                if path not in graph["generated_files"]:
                    raise ValueError("Missing captured literal platform metadata")
                input_file(path)
            record["outputs"] = target["outputs"]
            metadata[label] = record
        elif kind in ("group", "static_library", "source_set", "executable", "shared_library"):
            libraries[label] = capture_library(graph, target, record, input_file, label, SDK_LIBS)
            record["outputs"] = target.get("outputs", [])
            replaced_rust_flags = [flag for flag in record["gn_ldflags"] if flag.startswith("prebuilt_rustc_sysroot/lib/rustlib/x86_64-unknown-linux-gnu/lib/lib") and flag.endswith(".rlib")]
            if replaced_rust_flags:
                record["replaced_rust_toolchain_flags"] = replaced_rust_flags
            if label == "//third_party/wayland:wayland_scanner":
                record["native_configuration_headers"] = ["//third_party/wayland/include/config.h"]
            if label == "//components/url_formatter/spoof_checks/top_domains:top_domain_generator":
                record["native_tool_data"] = {"@electron_icu_sources//:common/icudtl.dat": "icudtl.dat"}
            linker_inputs = []
            for flag in record["gn_ldflags"]:
                if flag.startswith("-Wl,--version-script=../../"):
                    path = "//" + flag.removeprefix("-Wl,--version-script=../../")
                    input_file(path)
                    linker_inputs.append(path)
            record["linker_inputs"] = linker_inputs
        else:
            raise ValueError("Untranslated platform target kind: " + kind)
    input_file("//build/util/lastchange.py")
    actions[hook_label] = dict(
        name=hook_name, kind="action", gn_deps=[],
        script="build/util/lastchange.py", inputs=["//build/util/lastchange.py"], tools={},
        outputs=hook_outputs, runs=[dict(outputs=hook_outputs, args=["-m", "DAWN_COMMIT_HASH", "-s", "../../third_party/dawn", "--revision", "src/gpu/webgpu/DAWN_VERSION", "--header", "src/gpu/webgpu/dawn_commit_hash.h"])],
        response=[], environment={"BASE_COMMIT_HASH": dawn, "BASE_COMMIT_SUBMISSION_MS": "1759164973000"},
        checkout_hook={"source": "DEPS", "name": "lastchange_dawn", "command": original_command,
                       "commit_metadata": "https://github.com/google/dawn/commit/" + dawn},
    )
    for label, action in actions.items():
        ordering, visited, pending = set(), set(), list(action["gn_deps"])
        while pending:
            dependency = pending.pop()
            if dependency in visited or dependency not in seen:
                continue
            visited.add(dependency)
            if dependency in actions:
                ordering.add(dependency)
            elif targets[dependency]["type"] in ("group", "generated_file"):
                pending.extend(targets[dependency].get("deps", []))
        action["ordering_deps"] = sorted(ordering)
    for library in libraries.values():
        textual = set()
        for source in library["srcs"] + library["c_srcs"]:
            if source.startswith(BUILD):
                continue
            for include in re.findall(r'^\s*#\s*include\s*["<]([^"\n>]+\.(?:c|cc|cpp))[">]', physical(source[2:]).read_text(), re.M):
                candidates = [posixpath.normpath(posixpath.join(posixpath.dirname(source[2:]), include))]
                candidates += [posixpath.normpath(posixpath.join(directory, include)) for directory in library["includes"]]
                candidates += [include, posixpath.join("gen", include)]
                candidate = next((path for path in candidates if not path.startswith(("/", "../")) and (physical(path).is_file() or BUILD + path in producers or BUILD + path in graph["generated_files"])), None)
                if candidate is None:
                    raise ValueError("Missing original textual platform implementation: " + include)
                original = "//" + candidate if physical(candidate).is_file() else BUILD + candidate
                textual.add(original)
                input_file(original)
        if textual:
            library["textual_headers"] = sorted(textual)
    for path in sorted(files):
        if not physical(path).is_file():
            raise ValueError("Missing original platform input: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return dict(source_aliases=source_aliases, roots=ROOTS, graph_sha256=digest, source_revisions=revisions, names=names, libraries=libraries, actions=actions, metadata=metadata, literal_metadata=literal_metadata, execution_tools=sorted(set(tools.values())), execution_closure=sorted(execution_closure), producers=producers, headers=headers, files=sorted(files), external_files={path: shared[path] for path in sorted(used_shared)}, external={label: external[label] for label in sorted(used)}, generated_files=generated, toolchain_deps=sorted(TOOLCHAIN), sdk_libraries=sorted(SDK_LIBS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-root", action="append", default=[])
    args = parser.parse_args()
    roots = dict(item.split("=", 1) for item in args.source_root)
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, {name: Path(path) for name, path in roots.items()}, args.profiles)
    args.output.write_text(json.dumps(profile, indent=2) + "\n")


if __name__ == "__main__":
    main()

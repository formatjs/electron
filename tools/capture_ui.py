# SPDX-License-Identifier: MIT
"""Capture complete ui/base and the original WebUI resource/tool dependency closure."""

import argparse
import ast
import gzip
import hashlib
import json
import re
from pathlib import Path

from capture_mojo import SCRIPTS as MOJO_SCRIPTS
from native_graph import BUILD, capture_library, load_profiles

ROOTS = ["//ui/base:base"]
TOOLCHAIN = {"//buildtools/third_party/libc++:" + name for name in ("all_modules", "custom_headers", "libcxx_headers", "libc++")}
NODE = "//third_party/node/linux/node-linux-x64/bin/node"
PINS = {
    "node_modules": {"object_name": "e882f4f8be7b5fb8446e8f73ab1c49337f69dfb4", "sha256sum": "8b94d7c9daec96b6641175a1165afb288d0bfec967f26ece31be05b46302a4f6", "size_bytes": 9519115, "generation": 1754921648984973},
    "node": {"object_name": "fa98c6432de572206bc5519f85e9c96bd518b039", "sha256sum": "fb563633b5bfe2d4307075c54c6bb54664a3b5ec6bc811f5b15742720549007a", "size_bytes": 50288755, "generation": 1730835522207929},
}
SCRIPTS = MOJO_SCRIPTS | {"//" + name for name in ["build/write_buildflag_header.py", "ui/webui/resources/tools/generate_grd.py", "tools/grit/preprocess_if_expr.py", "tools/typescript/ts_library.py", "ui/webui/resources/tools/minify_js.py", "ui/webui/resources/tools/bundle_js.py", "ui/webui/resources/tools/eslint_ts.py", "tools/polymer/css_to_wrapper.py", "tools/typescript/path_mappings.py", "third_party/node/check_version.py", "tools/grit/grit.py", "tools/l10n/generate_locales_list.py", "tools/polymer/html_to_wrapper.py", "third_party/lottie/minify_lottie.py", "mojo/public/tools/bindings/minify_with_terser.py", "mojo/public/tools/bindings/concatenate-files.py"]}



def capture(graph, digest, chromium, node_modules, profiles):
    external, shared = load_profiles(profiles, [("base", "base"), ("embedder", "embedder"), ("ipcz", "ipcz"), ("libnode", "libnode"), ("perfetto", "perfetto_native"), ("protobuf", "protobuf"), ("v8_engine", "v8_engine"), ("v8_support", "v8_support"), ("network", "network"), ("mojo", "mojo"), ("fonts", "fonts"), ("codecs", "codecs"), ("skia", "skia"), ("gfx", "gfx"), ("display", "display"), ("events", "events")])
    targets, seen, pending = graph["targets"], set(), list(ROOTS)
    while pending:
        label = pending.pop()
        if label in seen or label in external or label in TOOLCHAIN:
            continue
        seen.add(label)
        pending.extend(targets[label].get("deps", []))
    names = {label: "target_" + hashlib.sha256(label.encode()).hexdigest()[:16] for label in sorted(seen)}
    deps = ast.parse((chromium / "DEPS").read_text())
    entries = next(item.value for item in deps.body if isinstance(item, ast.Assign) and any(isinstance(name, ast.Name) and name.id == "deps" for name in item.targets))
    for name, path in [("node_modules", "src/third_party/node/node_modules"), ("node", "src/third_party/node/linux")]:
        record = next(ast.literal_eval(value)["objects"][0] for key, value in zip(entries.keys, entries.values) if isinstance(key, ast.Constant) and key.value == path)
        if any(record.get(key) != value for key, value in PINS[name].items()):
            raise ValueError("WebUI DEPS source pin changed")
    roots = {"third_party/node/node_modules": node_modules}

    def physical(path):
        for prefix, root in roots.items():
            if path.startswith(prefix + "/"):
                return root / path[len(prefix) + 1:]
        return chromium / path

    files, generated, headers, used_shared = set(), {}, {}, set()
    producers = {}
    for label in sorted(seen):
        target = targets[label]
        if target["type"] in ("action", "generated_file", "copy"):
            for output in target["outputs"]:
                if not output.startswith(BUILD) or output in producers:
                    raise ValueError("Unexpected/duplicate UI output")
                producers[output] = label

    tools = {output: label for label, target in targets.items() if target["type"] == "executable" and (label in seen or label in external) for output in target.get("outputs", [])[:1]}

    def input_file(path):
        if path == NODE:
            return
        if path in tools:
            return
        if path in shared:
            used_shared.add(path)
            return
        if path.startswith(BUILD):
            if path in graph["generated_files"]:
                generated[path] = graph["generated_files"][path]
            elif path not in producers:
                raise ValueError("Unowned UI input: " + path)
        elif path.startswith("//"):
            files.add(path[2:])
        else:
            raise ValueError("Invalid UI source path")

    for directory in ["ui/base", "ui/color", "ui/gfx/mojom", "ui/lottie"]:
        root = chromium / directory
        inventory = sorted(path.relative_to(chromium).as_posix() for path in root.rglob("*") if path.is_file() and path.suffix in (".h", ".hpp", ".inc", ".inl"))
        if not inventory:
            raise ValueError("Missing original UI header inventory: " + directory)
        headers[directory] = inventory
        for path in inventory:
            input_file("//" + path)
    package_files = sorted("//third_party/node/node_modules/" + path.relative_to(node_modules).as_posix() for path in node_modules.rglob("*") if path.is_file())
    helpers = {}
    for directory in ["third_party/node", "tools/typescript", "tools/polymer", "tools/grit", "tools/l10n", "ui/webui/resources/tools", "third_party/lottie"]:
        helpers[directory] = sorted("//" + path.relative_to(chromium).as_posix() for path in (chromium / directory).rglob("*") if path.is_file() and path.suffix in (".py", ".js", ".json") and "__pycache__" not in path.parts)
    for path in package_files:
        input_file(path)
    actions, libraries, metadata, copies = {}, {}, {}, {}
    def generated_dependencies(label):
        outputs, visited, pending = set(), set(), list(targets[label].get("deps", []))
        while pending:
            dependency = pending.pop()
            if dependency in visited:
                continue
            visited.add(dependency)
            target = targets[dependency]
            if target["type"] in ("action", "action_foreach", "copy", "generated_file"):
                outputs.update(target.get("outputs", []))
            elif target["type"] != "group":
                continue
            pending.extend(target.get("deps", []))
        return outputs

    for label in sorted(seen):
        target = targets[label]
        if target["toolchain"] != "//build/toolchain/linux:clang_x64":
            raise ValueError("Expected captured Linux AMD64 UI profile")
        kind = target["type"]
        record = dict(name=names[label], kind=kind, gn_deps=target.get("deps", []))
        if kind == "action":
            if target["script"] not in SCRIPTS:
                raise ValueError("Untranslated original UI generator")
            directory_inputs = generated_dependencies(label)
            inputs = set(target.get("inputs", []) + target.get("sources", []) + [target["script"]]) | directory_inputs
            for directory, paths in helpers.items():
                if target["script"].startswith("//" + directory + "/"):
                    inputs.update(paths)
            uses_node = "node.RunNode(" in physical(target["script"][2:]).read_text()
            if uses_node:
                inputs.update(helpers["third_party/node"])
                inputs.update(helpers["tools/typescript"])
            args = [arg.replace("$SOURCE_ROOT/out/bazel-import/", "") for arg in target.get("args", [])]
            if target["script"] == "//mojo/public/tools/bindings/mojom_bindings_generator.py":
                prefix = {"c++": "cpp_templates.zip", "typescript": "ts_templates.zip", "javascript": "js_templates.zip"}[args[args.index("-g") + 1]]
                inputs.add(BUILD + args[args.index("--bytecode_path") + 1] + "/" + prefix)
            for arg in args:
                if arg.startswith("../../") and physical(arg[6:]).is_file():
                    inputs.add("//" + arg[6:])
                elif BUILD + arg in graph["generated_files"]:
                    inputs.add(BUILD + arg)
            if target["script"] == "//tools/grit/grit.py":
                for source in list(inputs):
                    if source.startswith("//ui/strings/") and source.endswith(".grd"):
                        inputs.update("//" + path.relative_to(chromium).as_posix() for path in (chromium / "ui/strings").rglob("*") if path.is_file() and path.suffix in (".xtb", ".grdp"))
            if any("{{" in arg.replace("{{response_file_name}}", "") for arg in args):
                raise ValueError("Untranslated UI generator placeholder: " + label)
            for path in sorted(inputs):
                input_file(path)
            execution_tools = {path: tools[path] for path in sorted(inputs) if path in tools}
            if uses_node or NODE in inputs:
                execution_tools[NODE] = "@electron_chromium_node_tool//:node-linux-x64/bin/node"
            record.update(generated_dependency_inputs=sorted(directory_inputs), node_modules=uses_node or NODE in inputs, script=target["script"][2:], inputs=sorted(path for path in inputs if path not in tools and path != NODE), tools=execution_tools, args=args, outputs=target["outputs"], response=target.get("response_file_contents", []))
            actions[label] = record
        elif kind == "copy":
            if len(target["sources"]) != len(target["outputs"]):
                raise ValueError("Untranslated original GN copy")
            for path in target["sources"]:
                input_file(path)
            record.update(sources=target["sources"], outputs=target["outputs"])
            copies[label] = record
        elif kind == "generated_file":
            for path in target["outputs"]:
                if path not in graph["generated_files"]:
                    raise ValueError("Missing captured literal UI metadata")
                input_file(path)
            record["outputs"] = target["outputs"]
            metadata[label] = record
        elif kind in ("group", "static_library", "source_set", "executable"):
            libraries[label] = capture_library(graph, target, record, input_file, label)
        else:
            raise ValueError("Untranslated UI target kind: " + kind)
    for label, record in actions.items():
        ordering, visited, pending = set(), set(), list(record["gn_deps"])
        while pending:
            dependency = pending.pop()
            if dependency in visited or dependency not in seen:
                continue
            visited.add(dependency)
            if dependency in actions or dependency in copies:
                ordering.add(dependency)
            elif targets[dependency]["type"] in ("group", "generated_file"):
                pending.extend(targets[dependency].get("deps", []))
        record["ordering_deps"] = sorted(ordering)
    textual_headers = set()
    for library in libraries.values():
        for path in library["srcs"] + library["c_srcs"]:
            if path.startswith(BUILD):
                continue
            for include in re.findall(r'^\s*#\s*include\s*"(third_party/[^"\n]+\.(?:c|cc))"', physical(path[2:]).read_text(), re.M):
                if not physical(include).is_file():
                    raise ValueError("Missing original textual implementation: " + include)
                textual_headers.add(include)
                input_file("//" + include)
    for path in files:
        if not physical(path).is_file():
            raise ValueError("Missing original UI input: " + path)
    used = {dep for label in seen for dep in targets[label].get("deps", []) if dep in external}
    return dict(roots=ROOTS, graph_sha256=digest, names=names, libraries=libraries, actions=actions, metadata=metadata, copies=copies, execution_tools=sorted(set(tools.values())), source_archives=PINS, node_modules_files=[path[2:] for path in package_files], producers=producers, headers=headers, textual_headers=sorted(textual_headers), files=sorted(files), external_files={path: shared[path] for path in sorted(used_shared)}, external={label: external[label] for label in sorted(used)}, generated_files=generated, toolchain_deps=sorted(TOOLCHAIN))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "chromium-root", "node-modules-root", "profiles", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    content = args.graph.read_bytes()
    profile = capture(json.loads(gzip.decompress(content)), hashlib.sha256(content).hexdigest(), args.chromium_root, args.node_modules_root, args.profiles)
    args.output.write_text(json.dumps(profile, indent=2) + "\n")


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: MIT
"""Original CrabbyAVIF source identity and native codec bindings."""

import ast
import hashlib
import re
from native_graph import value

ROOT = "//third_party/crabbyavif:crabbyavif"
BINDINGS = {"//third_party/crabbyavif:crabbyavif_" + codec + "_sys": codec for codec in ["dav1d", "libyuv"]}
CODECS = {"//third_party/" + codec + ":" + codec: "@electron_platform_sources//:target_" + hashlib.sha256(("//third_party/" + codec + ":" + codec).encode()).hexdigest()[:16] for codec in ["dav1d", "libyuv"]}


def source_identity(source):
    tree = ast.parse((source / "DEPS").read_text())
    assignments = {name.id: node.value for node in tree.body if isinstance(node, ast.Assign) for name in node.targets if isinstance(name, ast.Name)}
    variables = {key.value: val for key, val in zip(assignments["vars"].keys, assignments["vars"].values) if isinstance(key, ast.Constant)}
    dependencies = {key.value: val for key, val in zip(assignments["deps"].keys, assignments["deps"].values) if isinstance(key, ast.Constant)}

    def text(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return text(node.left) + text(node.right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Var" and len(node.args) == 1:
            return text(variables[ast.literal_eval(node.args[0])])
        raise ValueError("Unsupported original CrabbyAVIF revision expression")

    url = text(dependencies["src/third_party/crabbyavif/src"])
    remote, commit = url.rsplit("@", 1)
    if not remote.startswith("https://") or not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("Expected exact original CrabbyAVIF source pin")
    return {"remote": remote, "commit": commit}


def capture_binding(graph, source, label, checked_file, root_files):
    codec = BINDINGS[label]
    targets = graph["targets"]
    target = targets[label]
    generator = "//third_party/crabbyavif:crabbyavif_" + codec + "_bindings"
    action = targets[generator]
    copies = [dep for dep in target["deps"] if targets[dep]["type"] == "copy"]
    if len(copies) != 1 or action["script"] != "//build/rust/gni_impl/run_bindgen.py":
        raise ValueError("Unexpected original CrabbyAVIF binding producer")
    copy = targets[copies[0]]
    filename = codec + "_bindgen.rs"
    expected = {copies[0], "//build/rust/allocator:allocator", "//build/rust/chromium_prelude:chromium_prelude", "//build/rust/std:std"}
    if set(target["deps"]) != expected or copy["deps"] != [generator] or copy["sources"] != action["outputs"] or len(copy["outputs"]) != 1 or not copy["outputs"][0].endswith("/" + filename):
        raise ValueError("Unexpected original CrabbyAVIF binding copy layout")
    expected_deps = ["//third_party/dav1d:dav1d_headers"] if codec == "dav1d" else []
    if action["deps"] != expected_deps or len(action["sources"]) != 1:
        raise ValueError("Untranslated original CrabbyAVIF binding dependency")
    args = action["args"]
    begin, end = args.index("--bindgen-flags") + 1, args.index("--")
    header = checked_file(action["sources"][0][2:])
    root_files.add(header)
    native = "//third_party/" + codec + ":" + codec
    config_owner = native if codec == "dav1d" else "//third_party/libyuv:libyuv_internal"
    definitions = value(graph, targets[config_owner], "defines")
    if codec == "dav1d":
        definitions = [d for d in definitions if d.startswith(("CONFIG_LOG=", "HAVE_PTHREAD_", "DAV1D_API="))]
        if "DAV1D_API=" not in definitions:
            raise ValueError("Original dav1d public ABI configuration missing")
    else:
        definitions = [d for d in definitions if d == "CHROMIUM" or d.startswith("LIBYUV_")]
        if "CHROMIUM" not in definitions:
            raise ValueError("Original libyuv public configuration missing")
    config = "third_party/crabbyavif/BUILD.gn"
    config_file = source / config
    return {"owner": CODECS[native], "header": header, "header_label": "@electron_rust_sources//:" + header,
            "generated_filename": filename, "config_owner": config_owner, "bindgen_flags": ["--" + arg for arg in args[begin:end]],
            "clang_flags": ["-x", "c", "-std=c11", "-fparse-all-comments", "-fvisibility=default"] + ["-D" + d for d in definitions],
            "gn_args": args, "gn_deps": action["deps"], "gn_copy": copy,
            "config_label": "//third_party/" + codec + ":" + codec + "_config", "config_source": config, "config_source_sha256": hashlib.sha256(config_file.read_bytes()).hexdigest()}

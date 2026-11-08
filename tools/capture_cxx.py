# SPDX-License-Identifier: MIT
"""Capture original CXX bridge actions without merging Rust and C++ link ownership."""

import re
import hashlib
import struct
from native_graph import BUILD, capture_library


def capture_font_fixtures(source, skia, checked_file, root_files):
    flags = ["colrv0", "colrv1", "variable", "sbix", "cbdt_cblc", "cff2", "avar2"]
    fixtures = [
        ("third_party/blink/renderer/platform/testing/data/roboto-a.ttf", []),
        ("third_party/blink/renderer/platform/testing/data/colrv0_test.ttf", ["colrv0"]),
        ("third_party/blink/renderer/platform/testing/data/colrv1_test.ttf", ["colrv1"]),
        ("third_party/skia/resources/fonts/Variable.ttf", ["variable"]),
        ("third_party/skia/resources/fonts/sbix.ttf", ["sbix"]),
        ("third_party/skia/resources/fonts/cbdt.ttf", ["cbdt_cblc"]),
        ("third_party/skia/resources/fonts/test_glyphs-glyf_colr_1_variable.ttf", ["colrv1", "variable"]),
    ]
    records = []
    for path, expected in fixtures:
        root_files.add(checked_file(path))
        data = (skia / path.removeprefix("third_party/skia/") if path.startswith("third_party/skia/") else source / path).read_bytes()
        if data[:4] not in (b"\0\1\0\0", b"OTTO"):
            raise ValueError("Expected original SFNT font fixture")
        count = int.from_bytes(data[4:6], "big")
        tables = {}
        for index in range(count):
            tag, checksum, offset, size = struct.unpack_from(">4sIII", data, 12 + index * 16)
            if offset > len(data) or size > len(data) - offset:
                raise ValueError("Original font table escapes fixture")
            tables[tag] = data[offset:offset + size]
        required = {"variable": [b"fvar"], "sbix": [b"sbix"], "cbdt_cblc": [b"CBDT", b"CBLC"]}
        if any(tag not in tables for flag in expected for tag in required.get(flag, [])):
            raise ValueError("Original font fixture lacks expected table")
        for flag, version in [("colrv0", 0), ("colrv1", 1)]:
            if flag in expected and int.from_bytes(tables[b"COLR"][:2], "big") != version:
                raise ValueError("Original font fixture has unexpected COLR version")
        records.append({"file": path, "flags": expected, "mask": sum(1 << flags.index(flag) for flag in expected), "sha256": hashlib.sha256(data).hexdigest()})
    return records


def capture_bridges(graph, source, roots, crate_name, cppdeps, checked_file, root_files, selected):
    targets = graph["targets"]
    records = {}

    def cpp_input(path):
        if not path.startswith(BUILD):
            root_files.add(checked_file(path[2:]))

    for key, root in roots.items():
        generator = root + "_cxx_generated_gen"
        action, native = targets[generator], targets[root + "_cxx_generated"]
        rust_source = targets[root]["crate_root"]
        directory, filename = rust_source[2:].rsplit("/", 1)
        output_base = "gen/" + directory + "/" + filename
        outputs = [BUILD + output_base + suffix for suffix in [".h", ".cc"]]
        script = "//third_party/rust/cxx/chromium_integration/run_cxxbridge.py"
        if action["type"] != "action_foreach" or action["script"] != script or action["sources"] != [rust_source] or action["outputs"] != outputs or native["sources"] != outputs:
            raise ValueError("Unexpected original CXX generator: " + root)
        arguments = [arg.replace("{{source_gen_dir}}", "gen/" + directory).replace("{{source_file_part}}", filename).replace("{{source}}", "../../" + rust_source[2:]) for arg in action["args"]]
        if any("{{" in arg for arg in arguments):
            raise ValueError("Untranslated CXX generator argument")
        extra_rust = [dep for dep in native["deps"] if targets[dep]["type"] == "rust_library"]
        toolchain = {"//buildtools/third_party/libc++:" + item for item in ["all_modules", "custom_headers", "libcxx_headers"]}
        if set(native["deps"]) != {"//build/rust:cxx_cppdeps", generator} | toolchain | set(extra_rust) or any(dep not in selected for dep in extra_rust):
            raise ValueError("Untranslated CXX dependency")
        config = capture_library(graph, native, {}, cpp_input, root + "_cxx_generated")
        headers = re.findall(r'include!\("([^"\n]+)"\)', (source / rust_source[2:]).read_text())
        root_files.update(checked_file(path) for path in headers)
        python_inputs = [script[2:], "build/action_helpers.py", "build/gn_helpers.py"]
        root_files.update(checked_file(path) for path in python_inputs)
        record = {
            "root": root, "crate": crate_name(root), "generator": generator,
            "script": script[2:], "source": rust_source[2:],
            "python_inputs": python_inputs, "header_inputs": headers,
            "cppdeps": cppdeps, "extra_rust_deps": [crate_name(dep) for dep in extra_rust],
            "outputs": [path.removeprefix(BUILD) for path in outputs], "args": arguments,
            "gn_args": action["args"], "gn_inputs": action["inputs"], "gn_deps": action["deps"],
            "cpp_gn_deps": native["deps"], "copts": config["copts"], "defines": config["defines"],
            "omitted_toolchain_options": config["omitted_toolchain_and_diagnostic_flags"],
        }
        if key == "rust_crash":
            helper_label = "//third_party/blink/common/rust_crash:cpp"
            helper = targets[helper_label]
            if set(helper["deps"]) != {root} | toolchain:
                raise ValueError("Untranslated Rust crash callback dependency")
            record["helper"] = capture_library(graph, helper, {"kind": helper["type"], "gn_target": helper_label, "gn_deps": helper["deps"]}, cpp_input, helper_label)
        records[key] = record
    return records

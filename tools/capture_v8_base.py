# SPDX-License-Identifier: MIT
"""Import the exact Linux V8 base inventory and portable platform task slice."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    graph = json.loads(gzip.decompress(args.graph.read_bytes()))

    def value(target, key):
        result = target.get(key, [])
        return graph["pool"][result["pool"]] if isinstance(result, dict) else result

    libraries = {}
    for label, language in [("//v8:v8_libbase", "cflags_cc"), ("//v8:libm", "cflags_c"), ("//v8:v8_libplatform", "cflags_cc")]:
        target = graph["targets"][label]
        flags, omitted = [], []
        for flag in value(target, "cflags") + value(target, language):
            if flag == "-Werror" or flag == "-nostdinc++" or flag.startswith(("--sysroot=", "--target=", "-isystem../../", "-fcrash-diagnostics-dir=", "--warning-suppression-mappings=")):
                omitted.append(flag)
            else:
                flags.append(flag)
        sources = [path.removeprefix("//v8/") for path in target["sources"] if path.endswith((".cc", ".c"))]
        if label.endswith(":v8_libplatform"):
            selected = {"task-queue.cc", "delayed-task-queue.cc", "default-foreground-task-runner.cc", "default-worker-threads-task-runner.cc", "worker-thread.cc"}
            sources = [path for path in sources if Path(path).name in selected]
            if len(sources) != len(selected):
                raise ValueError("Expected all five captured platform task sources")
        definitions = value(target, "defines")
        libraries[label.split(":")[1]] = {"srcs": sources, "defines": [definition.replace('"', '\\"') for definition in definitions], "gn_defines": definitions, "copts": flags, "omitted_toolchain_and_diagnostic_flags": omitted}
    args.output.write_text('"""Exact Linux V8 base/task inventory; source toolchain paths use hermetic LLVM."""\n\nGRAPH_SHA256 = ' + repr(hashlib.sha256(args.graph.read_bytes()).hexdigest()) + '\n\nV8_BASE_LIBRARIES = ' + json.dumps(libraries, indent=4) + '\n')


if __name__ == "__main__":
    main()

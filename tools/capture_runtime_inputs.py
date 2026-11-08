# SPDX-License-Identifier: MIT
"""Capture original Linux distribution producers without building products."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

from native_graph import unpack_profile


def bazel_files(runtime, platform):
    overrides = {
        "LICENSE": ("//electron:electron_license", "@electron//source/distribution:LICENSE"),
        "LICENSES.chromium.html": ("//electron:chromium_licenses", "@electron//source/distribution:LICENSES.chromium.html"),
        "version": ("//electron:electron_version_file", "@electron//source/distribution:version"),
        "icudtl.dat": ("//third_party/icu:copy_icudata", "@electron_icu_sources//:common/icudtl.dat"),
        "snapshot_blob.bin": ("//v8:run_mksnapshot_default", "@electron_v8_engine_sources//:snapshot_blob.bin"),
        "resources/default_app.asar": ("//electron:default_app_asar", "@electron//source/default_app:default_app.asar"),
        "electron": ("//electron:electron_app", "@electron_platform_sources//:programs/electron"),
        "chrome-sandbox": ("//sandbox/linux:chrome_sandbox", "@electron_platform_sources//:programs/chrome-sandbox"),
        "chrome_crashpad_handler": ("//components/crash/core/app:chrome_crashpad_handler", "@electron_platform_sources//:programs/chrome_crashpad_handler"),
    }
    files = {}
    for path, entry in runtime["files"].items():
        producer, output = entry["target"], entry["output"]
        if path in overrides:
            original, label = overrides[path]
            if producer != original:
                raise ValueError("Distribution adapter producer changed: " + path)
        elif producer in platform["actions"]:
            if output not in platform["actions"][producer]["outputs"]:
                raise ValueError("Distribution output missing from native action: " + output)
            label = "@electron_platform_sources//:" + output.removeprefix(runtime["build_dir"])
        elif producer in platform["libraries"]:
            library = platform["libraries"][producer]
            if library["kind"] != "shared_library" or output not in library["outputs"]:
                raise ValueError("Distribution library differs from native producer: " + path)
            label = "@electron_platform_sources//:" + Path(output).name
        else:
            raise ValueError("Distribution input lacks a native provider: " + path)
        files[path] = label
    return files


def capture(project, source_root):
    targets = project["targets"]
    build = project["build_settings"]["build_dir"]
    if build != "//out/bazel-import/":
        raise ValueError("Expected the captured Linux build directory")
    credits = targets["//components/resources:about_credits"]
    if credits["type"] != "action" or credits.get("script") != "//tools/licenses/licenses.py":
        raise ValueError("Enable generate_about_credits; placeholder credits cannot form a release runtime")
    manifest = source_root / "electron/script/zip_manifests/dist_zip.linux.x64.manifest"
    paths = manifest.read_text().splitlines()
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate original distribution path")
    for path in paths:
        parsed = PurePosixPath(path)
        if not path or parsed.is_absolute() or str(parsed) != path or ".." in parsed.parts or "\\" in path:
            raise ValueError("Invalid original distribution path")
    producers = {}
    outputs = {}
    for label, target in targets.items():
        if target.get("toolchain") != project["build_settings"]["default_toolchain"]:
            continue
        for output in target.get("outputs", []):
            if output in outputs:
                raise ValueError("Ambiguous original runtime producer: " + output)
            outputs[output] = label
    files, omitted = {}, {}
    for path in paths:
        output = build + path
        if path == "chrome-sandbox" and output not in outputs:
            sandbox = targets["//sandbox/linux:chrome_sandbox"]
            if sandbox["type"] != "executable" or len(sandbox.get("outputs", [])) != 1:
                raise ValueError("Expected one original sandbox executable")
            output = sandbox["outputs"][0]
        if output not in outputs:
            if path == "libffmpeg.so" and targets["//third_party/ffmpeg:ffmpeg"]["type"] == "source_set":
                omitted[path] = "FFmpeg is linked into the executable"
                continue
            raise ValueError("Original distribution producer missing: " + path)
        label = outputs[output]
        files[path] = {"target": label, "output": output}
        producers[label] = targets[label]
    producers["//components/resources:about_credits"] = credits

    def normalized(value):
        if isinstance(value, str):
            return value.replace(str(source_root), "$SOURCE_ROOT")
        if isinstance(value, list):
            return [normalized(item) for item in value]
        if isinstance(value, dict):
            return {key: normalized(item) for key, item in value.items()}
        return value

    fields = ["type", "toolchain", "script", "args", "inputs", "sources", "outputs", "source_outputs", "deps",
              "depfile", "response_file_contents", "response_file_name"]
    records = {}
    for label, target in sorted(producers.items()):
        selected = fields if target["type"] in ("action", "action_foreach", "copy") else ["type", "toolchain", "outputs"]
        records[label] = normalized({field: target[field] for field in selected if field in target})
    return {
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "build_dir": build,
        "real_credits": True,
        "files": dict(sorted(files.items())),
        "omitted": omitted,
        "producers": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("project", "source-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--platform-profile", type=Path,
                        default=Path(__file__).resolve().parents[1] / "bcr/overlay/source/native/platform_inputs.json")
    args = parser.parse_args()
    raw = args.project.read_bytes()
    result = capture(json.loads(raw), args.source_root.resolve())
    result["gn_project_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    metadata = {key: result[key] for key in ("gn_project_sha256", "manifest_sha256")}
    metadata["producers"] = {label: result["producers"][label] for label in (
        "//electron:electron_version_file", "//electron:electron_license", "//electron:chromium_licenses")}
    args.output.with_name("runtime_metadata.bzl").write_text(
        '"""Captured original distribution metadata producers; do not edit."""\n\nRUNTIME_METADATA = json.decode(' +
        json.dumps(json.dumps(metadata, separators=(",", ":"))) + ")\n")
    files = bazel_files(result, unpack_profile(json.loads(args.platform_profile.read_text())))
    args.output.with_name("runtime_files.bzl").write_text(
        '"""Original distribution paths mapped to native Bazel producers; do not edit."""\n\nRUNTIME_FILES = ' +
        json.dumps(files, indent=4, sort_keys=True) + "\n")
    print(json.dumps({"files": len(result["files"]), "producers": len(result["producers"]), "omitted": result["omitted"]}))


if __name__ == "__main__":
    main()

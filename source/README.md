# Electron source import

Runtime packages still use official Electron binaries. Native source work:

- Electron39.0.0, Chromium142.0.7444.52 commit
  `7efca501bfcc84657ba2921a852e98ce1fb37641`, Node22.20.0 and V8
  `bb294624702efbb17691b642333f06bf5108e600` are pinned.
- Bazel's patch engine applies144 Chromium,55 Node and1 V8 patches.
- Patched libuv builds/links for five platforms; Linux test executes its
  Electron-specific loop-interrupt API. Windows uses MSVC.
- Real patched JS2C builds and emits embedder builtin C++ with separate host
  execution configuration. Electron fuse and Chromium buildflag generators
  produce actual Electron C++; native fuse-wire/default test passes.
- GN2285 (`81b24e01531e`) loads27,558 targets. Chromium's strict capture tool
  validates the complete11,955-target Electron closure,4,570 runtime entries
  and generated-file contents. `native/linux_amd64.partial.json.gz` records
  exact tool hashes, arguments and unfinished patch groups.

The metadata tree reuses matching-DEPS checkout files read-only. It must not
be used to compile or package Electron. BoringSSL, DevTools, FFmpeg, NAN,
Perfetto, Squirrel.Mac, Mantle, ReactiveObjC, WebRTC, reclient configuration
and SQLite patch stacks remain. Their archive pins and native targets,
Electron's locked npm bundling actions, snapshots and final linkage still need
implementation. [upstream_pins.json](upstream_pins.json) records exact dependency
URLs, revisions and ordered patch filenames for the next import. Other four
source graphs also remain. No GN/Ninja build runs
inside Bazel actions.

## Reproduce Linux metadata

From this repository, materialize source repositories and native generators:

```sh
bazel build //source:chromium_patches //source:v8_patches \
  //source:embedder_javascript @electron_node_sources//:electron_patches.json \
  @electron_cast_core_sources//:proto/proto.gni \
  @electron_glslang_sources//:BUILD.gn
electron_output_base=$(bazel info output_base)
electron_repositories="$electron_output_base/external"
electron_capture_dir=$(mktemp -d)
electron_source_root="$electron_capture_dir/src"
```

Set these to existing matching-DEPS Chromium source, pinned GN, hermetic LLVM
and actual rules_rs nightly compiler roots. Verified local setup:

```sh
electron_deps_cache=/tmp/chromium-migration-source
electron_gn=/tmp/chromium-gn/gn
electron_llvm_root="$electron_repositories/llvm++llvm_toolchain_minimal+llvm-toolchain-minimal-linux-amd64"
electron_chromium_tools=/home/dev/bcr_overlays/tools
# rules_rs nightly/2025-09-25, reporting rustc1.92.0-nightly caccb4d03.
electron_rust_root=/tmp/chromium-ci-root-bazel/4885d5fc792b2938a031e6df2b5a1a5e/external/rules_rs++toolchains+rustc_linux_x86_64_nightly_2025_09_25

python3 tools/prepare_source.py \
  --chromium="$electron_repositories/+electron+electron_chromium_sources" \
  --electron="$electron_repositories/+electron+electron_sources" \
  --node="$electron_repositories/+electron+electron_node_sources" \
  --v8="$electron_repositories/+electron+electron_v8_sources" \
  --deps-cache="$electron_deps_cache" --destination="$electron_source_root" \
  --dependency="third_party/cast_core/public/src=$electron_repositories/+electron+electron_cast_core_sources" \
  --dependency="third_party/glslang/src=$electron_repositories/+electron+electron_glslang_sources"
mkdir -p "$electron_source_root/out/bazel-import"
cat > "$electron_source_root/out/bazel-import/args.gn" <<EOF
import("//electron/build/args/all.gn")
is_debug = false
is_component_build = false
is_official_build = false
symbol_level = 0
chrome_pgo_phase = 0
target_os = "linux"
target_cpu = "x64"
override_electron_version = "39.0.0"
clang_base_path = "$electron_llvm_root"
clang_version = "23"
clang_use_chrome_plugins = false
rust_sysroot_absolute = "$electron_rust_root"
rustc_version = "$("$electron_rust_root/bin/rustc" -V)"
angle_build_tests = false
EOF
"$electron_gn" gen "$electron_source_root/out/bazel-import" \
  --root="$electron_source_root" --root-target=//electron:electron \
  --ide=json --json-file-name=project.json
"$electron_gn" desc "$electron_source_root/out/bazel-import" \
  //electron:electron_app runtime_deps --format=json \
  --root="$electron_source_root" --root-target=//electron:electron \
  > "$electron_capture_dir/runtime-raw.txt"
```

GN prints an unused `enable_linux_installer` warning before JSON because the
root target excludes Chromium installers. Preserve that warning separately;
extract JSON into a clean file before invoking the serializer:

```sh
python3 - "$electron_capture_dir" <<'PY'
import json, sys
from pathlib import Path
directory = Path(sys.argv[1])
raw = (directory / 'runtime-raw.txt').read_text()
(directory / 'runtime.json').write_text(json.dumps(json.loads(raw[raw.index('{\n'):])))
PY
python3 tools/capture_source.py --chromium-tools="$electron_chromium_tools" \
  --source-root="$electron_source_root" --llvm-root="$electron_llvm_root" \
  --rust-root="$electron_rust_root" --gn="$electron_gn" \
  --runtime-deps="$electron_capture_dir/runtime.json" \
  --output=source/native/linux_amd64.partial.json.gz
```

Cast Core uses an exact Git commit: its Gitiles archive stream returned
different SHA256 values for the same URL. GLSLang uses Chromium DEPS revision
`a57276bf558f5cf94d3a9854ebdf5a2236849a5a`, rather than ANGLE's standalone
revision. Both are real source repositories, with no placeholder GN files.

# Electron source import

This overlay builds native Electron source components. No target currently links
a full Electron executable. Source pins and build inputs live in `bcr/overlay/source`.
Stage a local registry first as shown in the root README; add its registry flags
to every Bazel command below. Native source work:

- Electron 39.0.0, Chromium 142.0.7444.52 commit
  `7efca501bfcc84657ba2921a852e98ce1fb37641`, Node 22.20.0 and V8
  `bb294624702efbb17691b642333f06bf5108e600` are pinned.
- Bazel applies all 14 ordered patch stacks: 236 upstream patches. Exact
  revisions and patch filenames live in upstream_pins.json; 718 modified source
  files are checked against patch_fingerprints.json.
- Patched libuv builds/links for five platforms; Linux test executes its
  Electron-specific loop-interrupt API. Windows uses MSVC.
- Real patched JS2C builds and emits embedder builtin C++ with separate host
  execution configuration. Full Node builtin generation also produces all
  370 registered modules, including 14 real original-fs outputs and target
  config.gypi. The config output matches upstream's GN-driven script
  byte-for-byte. This configuration is Linux AMD64 only; independent original-fs
  and embedder producers also execute under a Windows ARM64 target configuration.
  Electron fuse and Chromium buildflag generators
  produce actual Electron C++; native fuse-wire/default test passes. Full
  patched BoringSSL crypto/TLS compiles and passes RIPEMD160, cipher lookup
  and AES-CFB roundtrip checks. Crypto/TLS also cross-links all five platforms;
  Linux GNU 2.31 probe executes. Real Node macro-isolation generation passes
  a compiled push/undef/pop integration test.
- GN 2285 (`81b24e01531e`) loads 27,558 targets. Chromium's strict capture tool
  validates the complete 11,955-target Electron closure, 4,570 runtime entries
  and generated-file contents. `native/linux_amd64.partial.json.gz` records
  exact tool hashes, arguments, all 14 applied patch groups and fingerprint hash.

The metadata tree reuses matching-DEPS checkout files read-only. It must not
be used to compile or package Electron. All Electron patch groups are now
applied, including nested Squirrel/Mantle/ReactiveObjC dependencies. Other
Chromium dependencies still need explicit source/Bazel declarations before
full native translation. Other four source graphs also remain. No GN/Ninja
build runs inside Bazel actions.

Next concrete producers: `//third_party/electron_node:libnode` has 171 C/C++
units; `//electron:electron_lib` has 315. Node's `run_node_js2c`,
`generate_config_gypi` and `node_js2c_original_fs` now have native Bazel
producers. All eight Electron webpack bundles now build using actual upstream
configurations, captured buildflags and 141 integrity-pinned packages
from its exact yarn.lock. Pinned Node 22.20.0 comes from rules_nodejs execution
toolchains; this bootstrap is an official runtime, not source-built Node.
These bundles currently transpile without typechecking; TypeScript definition
generation remains unfinished. `@electron//source:electron_natives` runs actual C++ JS2C
with all eight canonical `electron/js2c/*` module names.
The Chromium importer then needs matching V8/Blink/content libraries, snapshot
producers and runtime packaging. No target currently links a source-built
Electron executable.

`bazel test @electron//tests:node_builtins_test` runs the actual full Node producer
chain. It checks regular fs and isolated original-fs registration/payloads,
native module ABI 140, NAPI 10, V8 sandbox/pointer compression and target
configuration embedded as JSON. No GN process runs inside these actions.

`@electron//tests:electron_bundles_test` parses all eight emitted bundles with
pinned Node and verifies lossless one-byte and two-byte C++ embedding. Earlier
app-level bundle smoke used official Electron binaries; that packaging example
now belongs with the future app rules repository. Source tests do not establish
that a source-built Electron runtime launches.

The npm closure includes exact required/optional lock dependencies, explicit
webpack/TypeScript peers and the config's terser import. This is a bounded
Electron source tool closure, not a general npm package manager. Packages copy
into a private staging tree; Node resolves their exact dependency links there.
No install hooks run; sandbox actions deny network on Linux.

The native BoringSSL overlay mirrors Electron's extra crypto source list. Its
GN list includes obsolete `decrepit/ripemd/internal.h`; that nonexistent header
is excluded, and the real `decrepit/macros.h` dependency is declared explicitly.

## Native Node dependencies

The Linux AMD64 profile now declares Ada, c-ares, HdrHistogram, llhttp, nghttp2,
simdjson, SQLite and uvwasi from the pinned patched Node tree. All 133 C/C++ units,
effective definitions and language-specific options come from the verified GN
capture. Hermetic LLVM supplies compiler/sysroot/libc++; omitted global include
roots and toolchain/diagnostic flags remain recorded. Unsupported dependency
edges fail import rather than substituting another library version.

`@electron//source:node_dependencies_test` links all eight libraries and checks
URL/JSON/HTTP parsing, IPv6 conversion, histogram recording, HTTP/2 settings,
SQLite FTS5/session configuration and WASI argument transfer.
[4cdf425 source components](https://formatjs.buildbuddy.io/invocation/2a3b5827-c0ff-4435-ba97-6922950889a4)
and [BCR consumer](https://formatjs.buildbuddy.io/invocation/af1a822c-1bd7-4b88-acc6-f961b36e278c)
both passed compilation and the linked probe. This does not link libnode or
Electron. Other target profiles remain unsupported for these libraries.

The expanded profile adds nbytes, ncrypto and header-only Postject: 136 compiled
units across ten libraries plus one header library. ncrypto uses the existing
Electron-patched BoringSSL provider; its GN include mapping remains recorded.
The linked probe checks unaligned byte swaps and invalid lengths, the
[RFC 5869 A.1 HKDF vector](https://www.rfc-editor.org/rfc/rfc5869.html#appendix-A.1)
and output-length limits, plus Postject lookup of a declared ELF note and missing
resources. The note is assembled by the execution toolchain. No host binary
editing tool or alternate crypto runtime is used. Hosted results must establish
this expansion before claiming validation.

Regenerate the inventory from the same graph:

```sh
python3 tools/capture_node_deps.py --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --output=bcr/overlay/source/native/node_deps_inputs.bzl
buildifier bcr/overlay/source/native/node_deps_inputs.bzl
```

## Native V8 base/task slice

`@electron_v8_sources//:libbase` compiles all 40 captured Linux AMD64 source
units; `:libm` compiles all three C units. `:platform_tasks` compiles five real
libplatform queue/foreground/worker units. These are static archives, using the
exact patched V8 revision and captured GN definitions. Source toolchain/sysroot
paths and warning-as-error policy are replaced by hermetic LLVM; every omitted
option remains recorded in `native/v8_base_inputs.bzl`. New Clang deprecation
warnings from pinned Abseil are expected and do not change source semantics.

`@electron_abseil_sources` exposes native Bazel rules from Abseil embedded in
the verified Chromium archive. It downloads no alternate Abseil version. The
GTest production header uses a real forwarding include to the declared BCR
header dependency. No substitute platform/tracing headers or functions exist.

`bazel test @electron//source:v8_tasks_test` executes 32 immediate worker tasks, delayed
worker/foreground scheduling, queue termination and captured libm sin/cos.
Only Linux AMD64 is supported by this native profile. Full libplatform still
needs Electron-patched Perfetto tracing and the remaining platform sources;
this slice does not initialize a V8 isolate or link Electron.

Refresh its exact inventory after graph capture:

```sh
python3 tools/capture_v8_base.py --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --output=bcr/overlay/source/native/v8_base_inputs.bzl
buildifier bcr/overlay/source/native/v8_base_inputs.bzl
```


## Reproduce Linux metadata

From this repository, materialize source repositories and native generators:

```sh
bazel build @electron//source:chromium_patches @electron//source:v8_patches \
  @electron//source:embedder_javascript @electron//source:dependency_patches \
  @electron_node_sources//:electron_patches.json \
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
# rules_rs nightly/2025-09-25, reporting rustc 1.92.0-nightly caccb4d03.
electron_rust_root=/tmp/chromium-ci-root-bazel/4885d5fc792b2938a031e6df2b5a1a5e/external/rules_rs++toolchains+rustc_linux_x86_64_nightly_2025_09_25

python3 - "$electron_repositories" "$electron_deps_cache" "$electron_source_root" <<'PY'
import json, subprocess, sys
from pathlib import Path
repositories, cache, destination = map(Path, sys.argv[1:])
def repository_path(name):
    if name == 'electron':
        return repositories / 'electron+'
    matches = list(repositories.glob('*+' + name))
    if len(matches) != 1:
        raise ValueError(f'Expected one repository for {name}: {matches}')
    return matches[0]
args = ['python3', 'tools/prepare_source.py',
        '--chromium=' + str(repository_path('electron_chromium_sources')),
        '--electron=' + str(repository_path('electron')),
        '--node=' + str(repository_path('electron_node_sources')),
        '--v8=' + str(repository_path('electron_v8_sources')),
        '--deps-cache=' + str(cache), '--destination=' + str(destination),
        '--patch-fingerprints=bcr/overlay/source/patch_fingerprints.json']
for entry in json.loads(Path('bcr/overlay/source/upstream_pins.json').read_text()):
    if entry['group'] in {'chromium', 'node', 'v8'}:
        continue
    name = 'electron_' + entry['group'].lower().replace('.', '_').replace('-', '_') + '_sources'
    args.append('--dependency=' + entry['repo'].removeprefix('src/') + '=' + str(repository_path(name)))
for path, name in [('third_party/cast_core/public/src', 'electron_cast_core_sources'),
                   ('third_party/glslang/src', 'electron_glslang_sources')]:
    args.append('--dependency=' + path + '=' + str(repository_path(name)))
subprocess.run(args, check=True)
PY
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
  --patch-fingerprints=bcr/overlay/source/patch_fingerprints.json \
  --output=bcr/overlay/source/native/linux_amd64.partial.json.gz
```

Cast Core uses an exact Git commit: its Gitiles archive stream returned
different SHA256 values for the same URL. GLSLang uses Chromium DEPS revision
`a57276bf558f5cf94d3a9854ebdf5a2236849a5a`, rather than ANGLE's standalone
revision. Both are real source repositories, with no placeholder GN files.

After recapturing the graph, refresh Node settings and exact builtin inventory:

```sh
"$electron_gn" args "$electron_source_root/out/bazel-import" --list --short \
  --root="$electron_source_root" \
  > "$electron_capture_dir/node-gn-args.txt"
python3 tools/capture_node_inputs.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --gn-args="$electron_capture_dir/node-gn-args.txt" \
  --generator="$electron_source_root/third_party/electron_node/tools/generate_config_gypi.py" \
  --settings=bcr/overlay/source/native/node_config_linux_amd64.json \
  --inventory=bcr/overlay/source/native/node_inputs.bzl
buildifier bcr/overlay/source/native/node_inputs.bzl
```

Refresh the bounded webpack lock/inventory from the same verified graph:

```sh
python3 tools/capture_webpack_deps.py --electron="$electron_source_root/electron" \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --lock=bcr/overlay/source/native/webpack_lock.json \
  --inventory=bcr/overlay/source/native/webpack_inputs.bzl \
  --flags=bcr/overlay/source/native/electron_buildflags.bzl
buildifier bcr/overlay/source/native/webpack_inputs.bzl bcr/overlay/source/native/electron_buildflags.bzl
```

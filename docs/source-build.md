# Electron source import

This overlay builds native Electron source components, including the complete
V8 engine, generated snapshots, Chromium base, patched libnode and native
Mojo/networking. No target
currently links a full Electron executable. Source pins and build inputs live in
`bcr/overlay/source`.
Compilation uses native Bazel rules and declared generators, without CMake or
`rules_foreign_cc` wrappers.
Stage a local registry first as shown in the root README; add its registry flags
to every Bazel command below. Desktop source targets use
`--platforms=@electron//source/platforms:linux_amd64`, matching the pinned
Chromium SDK’s glibc 2.31 floor. Development and consumer checks set this default;
cross probes select their own target platforms. Native source work:

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

Patched `//third_party/electron_node:libnode` now builds its 171 C/C++ units and
executes a real embedding probe. Next native producer:
`//electron:electron_lib` has 315 units plus its Chromium dependency closure. Node's `run_node_js2c`,
`generate_config_gypi` and `node_js2c_original_fs` now have native Bazel
producers. All eight Electron webpack bundles now build using actual upstream
configurations, captured buildflags and 141 integrity-pinned packages
from its exact yarn.lock. Pinned Node 22.20.0 comes from rules_nodejs execution
toolchains; this bootstrap is an official runtime, not source-built Node.
These bundles currently transpile without typechecking; TypeScript definition
generation remains unfinished. `@electron//source:electron_natives` runs actual C++ JS2C
with all eight canonical `electron/js2c/*` module names.
The remaining Chromium import needs matching Blink/content libraries and
runtime packaging. No target currently links a source-built
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

The Linux AMD64 profile declares Ada, c-ares, HdrHistogram, llhttp, nbytes, ncrypto,
nghttp2, Postject, simdjson, SQLite and uvwasi from the pinned patched Node tree.
Ten compiled libraries contain 136 C/C++ units; Postject is header-only. All
effective definitions and language-specific options come from the verified GN
capture. Hermetic LLVM supplies compiler/sysroot/libc++; omitted global include
roots and toolchain/diagnostic flags remain recorded. Unsupported dependency
edges fail import rather than substituting another library version.

`@electron//source:node_dependencies_test` consumes all eleven libraries and checks
URL/JSON/HTTP parsing, IPv6 conversion, histogram recording, HTTP/2 settings,
SQLite FTS5/session configuration and WASI argument transfer.
[9395812 source components](https://formatjs.buildbuddy.io/invocation/6f893782-be77-4e46-a6ff-030d79cdc260)
and [BCR consumer](https://formatjs.buildbuddy.io/invocation/52bfde1b-8468-476d-9866-109a133c1935)
both passed compilation and the linked probe. This does not link libnode or
Electron. Other target profiles remain unsupported for these libraries.

ncrypto uses the existing Electron-patched BoringSSL provider; its GN include
mapping remains recorded. The linked probe also checks unaligned byte swaps
and invalid lengths, the
[RFC 5869 A.1 HKDF vector](https://www.rfc-editor.org/rfc/rfc5869.html#appendix-A.1)
and output-length limits, plus Postject lookup of a declared ELF note and missing
resources. The execution toolchain assembles the fixture note, linked statically
into the main test executable because Postject searches that executable. No host
binary editing tool or alternate crypto runtime is used.

Regenerate the inventory from the same graph:

```sh
python3 tools/capture_node_deps.py --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --output=bcr/overlay/source/native/node_deps_inputs.bzl
buildifier bcr/overlay/source/native/node_deps_inputs.bzl
```

## Complete Torque generation

`@electron//source:v8_torque` builds the matching Torque compiler from 25 captured
C++ units and translates all 246 upstream `.tq` inputs into 1,250 declared engine
outputs. It preserves captured source order, exceptions/RTTI and Electron's
sandbox, Temporal, Intl and Perfetto definitions. Hermetic LLVM replaces source
toolchain/sysroot options; original dependencies, includes and omitted flags
remain recorded. No default V8 feature profile substitutes for this capture.

The action invokes the execution compiler directly through declared Python,
using stable source-relative arguments. The initial profile runs twice under
different source/output paths and input mtimes, then requires byte equality for
every output. A manifest records profile provenance and output hashes; output
groups expose headers and C++ sources for the remaining engine build. Tests
check generated engine/Intl/Temporal interfaces and malformed-input rejection.
Torque embeds its V8 root in source locations, so the runner passes `.` from
each isolated source directory. It also creates every declared output parent;
the upstream compiler assumes those directories already exist.

[93dc092 source components](https://formatjs.buildbuddy.io/invocation/0a295b37-7dc5-4a45-b395-e8e210eb1620)
and [BCR consumer](https://formatjs.buildbuddy.io/invocation/e338b62e-75ae-4a3e-b5fd-21279b2f4cd3)
passed complete generation, byte reproducibility, output hash/interface checks
and the real parser diagnostic/abort check. Core dumps are disabled for that
negative test. The cross-compile workflow also passed; this Torque profile
itself remains Linux AMD64. Full engine validation is recorded below; libnode
and the Electron executable remain unfinished.

```sh
python3 tools/capture_v8_torque.py --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --output=bcr/overlay/source/native/v8_torque_inputs.bzl
buildifier bcr/overlay/source/native/v8_torque_inputs.bzl
```

## Bytecode handler generation

`@electron//source:v8_bytecodes` builds the captured three-unit upstream
generator and emits `builtins-generated/bytecodes-builtins-list.h`. Interpreter
support is shared with a compiled probe; Torque and bytecode tools share the
same pinned header provider. All effective definitions and language options
come from the Electron graph. No GN wrapper, system interpreter or alternate
V8 profile runs in the generation action.

`@electron//source:v8_bytecodes_test` compiles the actual generated handler
macro and checks every opcode at all three operand scales against V8's
interpreter API: handler names, coverage, uniqueness, illegal wide encodings
and dense wide/extra-wide dispatch indices. A second generation uses a
different output path containing spaces; the probe compares all bytes.
Production consumers depend only on the first generation. Hosted validation
passed in [1395ef7 components](https://formatjs.buildbuddy.io/invocation/939077e6-f2cf-4874-8d8f-99b8becb0f72)
and [BCR consumer](https://formatjs.buildbuddy.io/invocation/4dedcd9e-2880-4aec-8a0e-d2fbacf123e4),
including the existing full Torque checks. This does not link the V8 engine.

```sh
python3 tools/capture_v8_bytecodes.py --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --output=bcr/overlay/source/native/v8_bytecode_inputs.bzl
buildifier bcr/overlay/source/native/v8_bytecode_inputs.bzl
```

## Regexp special-case generation

`@electron//source:v8_regexp` builds the captured `gen-regexp-special-case`
execution tool against matching patched V8 and Chromium ICU, then emits real
`src/regexp/special-case.cc`. It preserves the complete Electron definitions and
source flags. Bytecode and regexp generation share a direct Bazel action;
neither invokes the GN Python wrapper.

The compiled `@electron//source:v8_regexp_test` consumes those generated tables
and disables ambient ICU data-file access. It checks legacy ignore-case
matching for Kelvin sign, long s, sharp s, Greek mu and ordinary ASCII, plus
surrogate/canonicalization boundaries. A second output path contains spaces;
every generated byte must match.
[b98e496 components](https://formatjs.buildbuddy.io/invocation/3bc9b5ed-9f34-4053-ba0f-808adc539d5b)
and [BCR consumer](https://formatjs.buildbuddy.io/invocation/e936e28b-4f42-4864-96be-8c7127086717)
passed these checks and existing source tests. Cross-compile CI also passed;
this producer remains Linux AMD64.

V8's repository BUILD file now delegates to a stable source macro. Further
native rule edits do not need to change the BUILD template read during source
repository setup. The existing bytecode inventory regenerates byte-for-byte
after sharing its capture logic with the new generator. Full V8/Electron
linking remains unfinished.

```sh
python3 tools/capture_v8_generators.py --generator=regexp \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --output=bcr/overlay/source/native/v8_regexp_inputs.bzl
buildifier bcr/overlay/source/native/v8_regexp_inputs.bzl
```

## Matching Chromium ICU

`@electron_icu_sources//:icu` declares all 445 captured C++ units: 202 common
units, including upstream stub data, and 243 i18n units. Source revision
`1b2e3e8a421efae36141a7b932b41e315b089af8` and archive integrity match
formatjs/chromium's ICU overlay; repository setup also verifies the revision
against Electron's patched Chromium DEPS. Compile options, RTTI, definitions,
headers and dependency edges come from this Electron capture.
The header inventory includes GN's separate public lists and the real
`stubdata.h` include omitted from those lists. Upstream subset Bazel packages
are replaced by this captured graph; ICU sources and data remain unchanged.

The profile retains file-backed data. `common/icudtl.dat` is declared runtime
data for later packaging, rather than host ICU data or a different
ICU version. `@electron//source:icu_test` disables ambient data-file loading,
rejects corrupt common data, then initializes from that declared file. It
checks NFC composition, case-fold preflight/expansion, collation strengths,
French number formatting and Chromium's patched word-break behavior.
[fe62420 source components](https://formatjs.buildbuddy.io/invocation/63616e6c-424b-4f71-8962-5903b4a10113)
and [BCR consumer](https://formatjs.buildbuddy.io/invocation/23d317a4-9381-4466-a904-6afb3bb4a61d)
passed all compilation and these behavior checks; cross-compile CI also passed.
This captured ICU profile itself remains Linux AMD64. Its repository rule is
separate from Node/V8 repository implementations so future ICU setup edits do
not change their definition files. `//:source_components` requests both actual
ICU archives through `//source:icu_libraries`; building the dependency-only C++
provider alone would not request both archives. The full engine now consumes
these archives; final Electron linking remains unfinished.

The build-only component phase uses `--remote_download_outputs=minimal` so
compile-only archives remain in BB CAS. The following test phase retains
top-level downloads for its executables and declared runtime data.

```sh
python3 tools/capture_icu.py --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --output=bcr/overlay/source/native/icu_inputs.bzl
buildifier bcr/overlay/source/native/icu_inputs.bzl
```

## Captured PartitionAlloc

Temporal's Rust closure uses Chromium's allocator. The matching native
PartitionAlloc profile contains 66 C++ units across allocator base, core and
shim archives. An isolated repository projects these source bytes read-only
from the exact patched Chromium tree; it downloads no alternate version.
Captured flags and upstream buildflag generation retain the malloc shim,
backup-ref-pointer and thread-isolation settings.

`@electron//source:partition_alloc_test` links the real shim and checks heap
ownership, allocation/zeroing, realloc preservation and failed-realloc safety,
overflow handling and aligned allocation/reallocation. A child process checks
the upstream SIGILL trap on calloc multiplication overflow and SIGTRAP on
allocation-metadata overflow, with core dumps disabled. A valid huge request
and failed realloc must still return null.
It also checks that
ordinary `malloc` and C++ `new` use PartitionAlloc. No replacement allocator or
allocation stub supplies this prerequisite.
[5b7f211 source components](https://formatjs.buildbuddy.io/invocation/c0fd8cbf-f5c9-4994-a64a-c6dec789b10b)
and [BCR consumer](https://formatjs.buildbuddy.io/invocation/e50d8faf-cf75-49ac-8891-b726caf63db5)
passed archive compilation and all probe boundaries. Cross-compile CI also
passed; this PartitionAlloc profile itself is Linux AMD64. The following
Temporal slice now links this allocator through its original Rust bridge.

```sh
python3 tools/capture_partition_alloc.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --source-root=/path/to/matching/patched/chromium \
  --output=bcr/overlay/source/native/partition_alloc_inputs.bzl
buildifier bcr/overlay/source/native/partition_alloc_inputs.bzl
```

## Temporal Rust and allocator FFI

The captured Temporal closure declares 57 Rust targets from 44 pinned vendor
packages, including six original build scripts, proc macros and both allocator
variants. Three C++ bridge variants use Chromium's original allocator/error
handler sources. Runtime Rust keeps `rust_allocator_uses_allocator_impls_h` and
real PartitionAlloc-backed FFI; host variants retain their captured settings.
Native bindgen generates the original `bindings.rs` namespace wrapper inputs.

`hermeticbuild/rules_rs` 0.2.1 supplies native Rust actions. Development and BCR
consumer configurations register nightly/2025-09-25 and select the nightly
channel. Compiler target/metadata choices come from those declared providers;
captured features, editions, codegen and warning options remain explicit.
Source projection lists every crate input, checks Cargo.toml versions and maps
generated OUT_DIR/CARGO_MANIFEST_DIR paths. Dependencies come from the captured
graph; original build scripts run against declared inputs.

The one-unit V8 `ZoneInfo64Provider` uses its real upstream implementation and
the captured engine flags. `@electron//source:temporal_test` initializes declared
ICU data with ambient data-file loading disabled, then checks Rust allocation
ownership and fallible reserve, leap dates, rejection/constraining, calendar
arithmetic, Japanese calendar data and New York DST/gap behavior through that
actual provider.
[3278609 source components](https://formatjs.buildbuddy.io/invocation/df7fed7a-c08b-46f4-be2d-dcb6467631df),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/75b513b8-c73b-4fb4-a035-0122c0ed452d)
and [cross-compile checks](https://formatjs.buildbuddy.io/invocation/a9818842-360f-4d7f-ad60-29fd3732546c)
passed. This Linux AMD64 slice does not link the full V8 or Electron engine.

```sh
python3 tools/capture_temporal.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --source-root=/path/to/matching/patched/chromium \
  --fontconfig-root=/path/to/fontconfig-f0ed9c3f43161d3555f6f7a5234b22fe7ca60727 \
  --skia-root=/path/to/skia-f4ed99d2443962782cf5f8b4dd27179f131e7cbe \
  --output=bcr/overlay/source/native/temporal_inputs.json \
  --v8-output=bcr/overlay/source/native/v8_temporal_inputs.bzl
buildifier bcr/overlay/source/native/v8_temporal_inputs.bzl
```

## Full V8 engine and snapshots

The complete patched V8 engine now builds, links and executes. Native consumers
use `@electron_v8_engine_sources//:v8`, `:platform` and declared `:runtime` data.
Its 34 native targets add 1,453 C++/assembly compilation units; existing
libbase/libm and execution generators remain shared dependencies. Inspector uses
original compatibility checks, templates and declared Jinja2/MarkupSafe inputs.
FP16 uses Chromium's exact DEPS revision and a hashed archive.

```mermaid
flowchart LR
  Generators[Native Torque / bytecode / regexp] --> Core[V8 core / compiler / initializers]
  Inspector[Declared inspector generator] --> Core
  Core --> Mksnapshot[Native mksnapshot]
  Mksnapshot --> Snapshot[Startup blob / embedded assembly]
  Core --> Engine[Linked V8]
  Snapshot --> Engine
  Engine --> Probe[JS / Wasm / Intl / Temporal / inspector probe]
```

The profile projects 3,047 declared files. Generated layout aliases reuse
all 1,250 Torque outputs and the existing native producer. Snapshot creation
keeps the captured architecture/OS, predictable mode and seed `314159265`.
Upstream `mksnapshot` calls `CpuFeatures::Probe(true)`, disabling host CPU
probing for target code generation. Each native Python action, including
snapshot generation, requires byte equality across changed staging paths and
input mtimes. `:runtime` exposes the generated startup blob and matching ICU data.

The hermetic SDK needs explicit `<atomic>`/`<memory>` includes in Wasm `pgo.h`.
`v8_header_compat.patch` applies only to an owned projection copy; parent patched
V8 sources stay unchanged. `native_toolchain_patches.json` records that boundary.
The shared header provider exposes matching native Abseil dependencies instead
of relying on GN's implicit include-root access. Captured feature flags remain
intact, including pointer compression, sandbox, Intl and Perfetto.

`@electron//source:v8_engine_test` initializes the actual generated snapshot and
ICU data, executes a Wasm add function, JS collection operations, Unicode/locale
behavior and Rust-backed Temporal DST/rejection paths. It dispatches inspector
`Runtime.evaluate`, checks the decoded result, tests syntax-error reporting and
checks context state after collection.
[4516ed7 components](https://formatjs.buildbuddy.io/invocation/4d39e515-418d-4f13-a1ec-2a4b5484c4d0),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/ec9a0537-868a-4182-9ec0-ded5e613b4ef)
and [cross checks](https://formatjs.buildbuddy.io/invocation/4340b427-110a-46b5-a4be-84f4828020d0)
passed. This full engine profile remains Linux AMD64. Patched libnode,
Electron/Chromium content linking and complete runtime packaging remain open.

```sh
python3 tools/capture_v8_engine.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --v8-root=/path/to/matching/patched/v8 \
  --chromium-root=/path/to/matching/patched/chromium \
  --fp16-root=/path/to/pinned/FP16 \
  --output=bcr/overlay/source/native/v8_engine_inputs.json
```

## Complete captured Perfetto closure

The native profile translates all 329 captured Perfetto targets plus matching
JsonCpp: 68 original generator actions, 721 generated outputs and 564 C++
compilation units, including generated protocol implementations and host
plugins. Source sets retain object inclusion semantics; each target keeps its
captured compiler flags, definitions and dependencies.

Perfetto comes from Electron's patched `d5bbee7afdf259af4212929ccbff467dd5349953`
source. JsonCpp uses Chromium's exact DEPS revision
`42e892d96e47b1f6e29844cc705e148ec4856448` and a hashed archive, rather than a
newer BCR version. Its iterator `.inl` is a declared implementation input.
The projection declares 1,463 source/header/schema/script/license files.

The original protoc wrapper, buildflag writer, descriptor/table generators and
stamp script run through a declared Python action. Native protoc/plugins are
execution-platform inputs. Child processes get isolated Python, empty `PATH`
and an explicit environment. Every generator runs twice with different staging
paths, including spaces, and different source mtimes; output bytes must match.
The registered LLVM toolchain supplies the compiler-runtime archive formerly
named through GN's `$LLVM_ROOT`; no source action resolves that host path.

`@electron//source:perfetto_test` starts/stops real in-process tracing, decodes
packet-scoped interned names and debug annotations, and checks disabled-category
filtering. It also checks binary-string JsonCpp roundtrips and its captured
abort-on-invalid-conversion behavior, with core dumps disabled.
[7177c35 components](https://formatjs.buildbuddy.io/invocation/3072778c-6b5f-4d26-ad16-aa721e45c7f4),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/781d378c-801e-46f9-a1a9-45bfd2007deb)
and [cross checks](https://formatjs.buildbuddy.io/invocation/73a5d16b-bf93-4f1a-8e97-25159bb6bb41)
passed. These native profiles remain Linux AMD64. The full engine now consumes
this tracing closure; final Electron linking remains open.

```sh
python3 tools/capture_perfetto.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --chromium-root=/path/to/matching/patched/chromium \
  --perfetto-root=/path/to/matching/patched/perfetto \
  --jsoncpp-root=/path/to/pinned/jsoncpp \
  --output=bcr/overlay/source/native/perfetto_inputs.json
```

## Matching Protobuf runtime and compiler

Perfetto's generators require a matching protocol tool/runtime. The native
profile builds Chromium's embedded Protobuf 32.0 rather than substituting the
newer BCR module. Twelve original targets contain 129 C/C++ units: UTF-8 support,
full/lite runtimes, protoc, its C++/Java/Python compiler libraries and the original
JavaScript plugin dependency. That plugin uses Chromium's exact DEPS revision
`e6d763860001ba1a76a63adcff5efb12b1c96024` with a hashed archive.

The profile declares 1,110 source/header/schema/license files, preserves captured
compiler flags and keeps `GOOGLE_PROTOBUF_NO_RTTI` and
`PROTOBUF_INTERNAL_BOUNDS_CHECK_MODE_ABORT` consistent through generated code.
Abseil comes from the matching Chromium tree. Its public `base` target carries
the private raw-logging dependency; no visibility override or duplicate source
copy is needed. Protoc is an explicit execution-platform binary with its plugin
runfiles. Source sets keep their object inclusion semantics.

`@electron//source:protobuf_test` compiles full and lite schemas using that
source-built protoc. It checks packed signed values, binary maps, oneof/optional
presence, full/lite unknown-field preservation, dynamic reflection, truncated
messages, malformed packed fields and invalid UTF-8.
[687dc7f components](https://formatjs.buildbuddy.io/invocation/a70db8a5-8eee-417a-9cfd-53c1564ad657),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/e87c3f3f-4c89-4a11-9d22-0ce75b75d180)
and [cross checks](https://formatjs.buildbuddy.io/invocation/21521a1e-126f-4532-a745-8c2b84650786)
passed. These new profiles remain Linux AMD64. Perfetto's protocol/runtime
closure now uses this matching compiler and runtime.

```sh
python3 tools/capture_protobuf.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --chromium-root=/path/to/matching/patched/chromium \
  --javascript-root=/path/to/pinned/protobuf-javascript \
  --output=bcr/overlay/source/native/protobuf_inputs.json
```

## V8 number, SIMD and compression dependencies

Twelve captured targets expose Dragonbox, fast_float, Highway, simdutf and
Chromium zlib, including all four zlib SIMD helper targets and the portable
compression wrapper. Twenty-nine original C/C++ units retain their captured
language flags and SIMD definitions. Header-only targets remain header-only;
source sets keep their object inclusion semantics.

Dragonbox, fast_float and Highway use exact Chromium DEPS revisions and hashed
archives. Separate source repositories keep archive extraction independent of
profile edits. A read-only projection declares 179 source/header/license inputs;
simdutf, zlib and build headers come from the matching Chromium archive.
`tools/capture_v8_support.py` checks DEPS pins and rejects unknown dependencies,
source paths and include roots. Its `--help` lists the required source roots.

`@electron//source:v8_support_test` checks shortest-decimal roundtrips through
Dragonbox and fast_float, including subnormal/minimum/maximum doubles, overflow
and invalid input. It checks Unicode conversion and malformed UTF-8, Highway CPU
discovery/aligned memory, zlib/gzip/raw compression roundtrips, undersized output,
corrupt checksummed streams and CRC32/Adler32 vectors.
[51e5642 components](https://formatjs.buildbuddy.io/invocation/37462791-7cbe-4105-8610-3bfde508c7bc),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/11a4a3fd-25ce-4651-8115-0773a0923553)
and [cross checks](https://formatjs.buildbuddy.io/invocation/7766ab37-94e9-43d4-94f9-3c0f1469505e)
passed. The new library profiles themselves remain Linux AMD64. The full engine
now consumes them; Node/Electron integration remains open.

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

## Chromium base prerequisite

Node's original Chromium inspector protocol implementation depends on complete
`//base:base`. The native capture keeps that implementation and translates its
425-unit root plus support libraries: 448 C/C++ units total. The profile records
all source flags and omitted GN toolchain paths. Native LLVM replaces sysroot
compiler flags; pinned source-built GLib supplies Linux desktop interfaces.
Linux syscall support matches Chromium's exact `ed31caa` DEPS revision.

```mermaid
flowchart TD
  SDK[Pinned Rust SDK] --> CXX[Original CXX compiler and wrappers]
  CXX --> Bridges[Rust logger and JSON bridges]
  Generators[Original buildflags and protobuf generators] --> Base[Chromium base]
  Bridges --> Base
  GLib[Pinned native GLib] --> Base
  Existing[PartitionAlloc / ICU / Perfetto / BoringSSL] --> Base
  Base --> Inspector[Chromium inspector protocol]
  Inspector --> Node[Patched libnode]
```

`electron_base_sources` projects declared files read-only. Generated build dates
use the captured fixed timestamp; version generation consumes declared version
files. Python generators retain isolated interpreters, empty child `PATH`,
explicit environments and path/mtime byte checks. CXX configuration comes from
the pinned target Rust compiler; the CXX executable uses the execution platform.
Cargo does not resolve dependencies. The combined Temporal/base closure contains
85 Rust targets from 65 vendored packages; existing Temporal crates stay shared.

The linked probe exercises original Rust JSON parsing, strict/malformed input
rejection, JSON serialization, Base64 and native GLib task/idle dispatch.
[4746f81 components](https://formatjs.buildbuddy.io/invocation/88a49452-4b2d-4562-b922-e1cd177016cb),
[consumer](https://formatjs.buildbuddy.io/invocation/37a9576f-eea3-4c65-8205-6dabc9b3426e)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/56160928-3964-45f8-9578-6cd78f14d964)
checks passed. Base itself remains Linux AMD64; the cross check covers existing
platform probes. Complete libnode and Electron linking remain separate work.

Base also links PartitionAlloc's original two-unit `raw_ptr` implementation.
This is distinct from its 66-unit allocator/shim closure. Its private headers
stay separate from the existing allocator header target, keeping the full V8
engine's action inputs unchanged during this extension.

## Patched libnode and native inspector

`electron_libnode_sources` translates the 171-unit patched libnode source set,
original Chromium inspector protocol implementation and matching Brotli/Zstd
libraries: 239 C/C++/assembly units total. Existing V8, Base, ICU, BoringSSL,
libuv, eleven Node dependencies and both JS2C outputs stay shared.

```mermaid
flowchart TD
  Node[Patched Node sources and builtins] --> Library[libnode]
  Protocol[Original PDL and inspector generators] --> Library
  V8[Source-built V8 and startup snapshot] --> Library
  Base[Chromium Base and original CRDTP] --> Library
  Compression[Pinned Brotli / matching Zstd] --> Library
  Library --> Probe[Real Node environment and inspector]
  Addon[Native Node-API 10 shared addon] --> Probe
```

Native actions declare the PDL files read by Node's actual inspector config,
including a read-only alias to the matching patched V8 PDL. They also declare
the original generator's imported `Runtime.h`, omitted from captured GN outputs.
Zstd compression is an explicit extra native dependency: Node 22.20 exposes
compression APIs, while the captured GN edge only names the decoder. The
profile preserves original GN outputs/dependencies alongside these additions.
Zstd uses Chromium's exact `89d685e` DEPS revision and an integrity-pinned archive.
No stock Node/V8 source tree substitutes for Electron's selected versions.

Generators retain isolated Python, declared Jinja/MarkupSafe sources, empty
child `PATH`, explicit environments and output equality across paths/mtimes.
Compression header groups stay separate from Node headers; static-library and
source-set linkage retain their original distinction. Legacy GNU `-latomic`
resolves to the declared LLVM compiler-rt builtins archive, whose source includes
the atomic implementation. A native `cc_shared_library` builds the
addon; a declared pinned-Python action materializes unchanged bytes in a regular
`.node` file. Symlinking a `.so` is insufficient: Node resolves the real filename
before selecting its loader. Bazel 9 rejects a direct `.node` shared-library
filename, so the final file requires its own declared action.

`node_embed_lifecycle.patch` updates the owned `CommonEnvironmentSetup` copy to
dispose its isolate before unregistering the platform, matching Electron's
existing `NodeMainInstance` ordering. V8 can still request foreground tasks
during disposal. Original parent sources remain unchanged;
`native_compat_patches.json` records this compatibility patch.

The embedding probe initializes an actual Node environment with generated V8
startup data. It checks ABI 140, Node-API 10 shared-addon loading, original-fs,
asynchronous filesystem reads, crypto, Brotli/Zstd round trips and corruption
rejection, in-memory SQLite and inspector `Runtime.evaluate`. Generic 24-byte
atomic compare-exchange/load exercises the actual compiler-rt implementation.
[40b2baf components](https://formatjs.buildbuddy.io/invocation/db60fdd2-5715-468b-aad5-05013a89fa46),
[consumer](https://formatjs.buildbuddy.io/invocation/257b7fb2-b546-4a98-8b6a-6e1cfb45fa73)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/3e5b2b22-6b6f-4636-b582-5bc4efd1af57)
checks passed. libnode itself remains Linux AMD64; cross checks still cover the
existing platform probes. A complete Electron executable and the other full
source profiles remain unfinished.

## Gin and Base i18n

`electron_embedder_sources` adds the matching 32-unit Gin library, 20-unit Base
i18n library and four-unit CED library. Base, V8, ICU, Abseil and native GLib stay
shared. CED matches Chromium's exact `ba412eaa` DEPS revision and the independently
pinned archive used by `formatjs/chromium`.

```mermaid
flowchart TD
  Flags[Original fixed buildflag generators] --> Gin[Gin]
  V8[Native V8 and generated startup blob] --> Gin
  Base[Chromium Base] --> Gin
  ICU[Matching ICU and declared data] --> I18n[Base i18n]
  CED[Pinned original CED] --> I18n
  Base --> I18n
  Gin --> Electron[Electron / Blink / content]
  I18n --> Electron
```

Header groups remain separate; adding embedder sources does not change existing
Base/V8 headers or compiler inputs. Buildflag generators retain explicit inputs,
isolated Python and path/mtime byte checks. Captured context-snapshot and sandbox
flags remain enabled. The utility-isolate probe loads the generated default V8
snapshot; creating Blink's additional-context snapshot remains separate work.

The probe exercises original ICU descriptor initialization, Unicode folding,
legacy conversion, malformed UTF-8 rejection, word/grapheme boundaries and CED
detection. It creates a real Gin isolate/context, installs a C++ callback, checks
JS argument rejection and UTF-8 conversion, allocates through Gin's sandboxed
ArrayBuffer allocator and verifies the binding after GC and during shutdown.
The probe passes declared files through Base/Gin's file APIs; Gin's filename API
expects an asset basename. No host asset search path is needed.
[5bca689 components](https://formatjs.buildbuddy.io/invocation/fa47e627-5c1f-48a3-bba0-a3242d1f8dc6),
[consumer](https://formatjs.buildbuddy.io/invocation/93435deb-d75a-4138-a291-8f1c2c115443)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/f22772db-5323-4a1d-95be-d497d50030c6)
checks passed. This full profile remains Linux AMD64; full Electron still needs
linking.

## IPCz

`electron_ipcz_sources` builds all five captured Chromium IPCz source sets: 36
original C++ units, matching Chromium Base and shared Abseil. Source sets retain
whole-archive linkage; `IPCZ_STANDALONE` stays absent. Files project read-only
from Electron's exact Chromium archive. No independent IPCz checkout or
standalone support implementation substitutes for that configuration.

The integration probe builds four original synchronous reference-driver units
for testing only. Broker/client nodes exchange a 65,537-byte binary payload,
preserve required size after insufficient receive capacity, transfer a portal,
communicate through that portal and report peer closure. Invalid API/handle
calls and cleanup are checked too.
[c961819 components](https://formatjs.buildbuddy.io/invocation/f6a3b332-0992-416c-9457-6c23dbbb6324),
[consumer](https://formatjs.buildbuddy.io/invocation/3afbac9c-cb0e-4445-a246-0b6d499ffcde)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/99392287-c350-44ac-997e-d3e17c87b1e9)
checks passed. This full profile remains Linux AMD64. Mojo/network integration
follows below.

## Mojo and networking

`electron_network_sources` translates the complete captured Mojo embedder
closure: 1,124 C/C++ units in 63 library/group/tool targets, plus 29 original
generator runs. Existing Base, ICU, IPCz, Protobuf, compression and tracing
targets stay shared. QUICHE and RE2 use Chromium's exact DEPS revisions; SQLite
uses Electron's patched source, original shim and symbol-renaming headers.
Source-listed headers, public headers and included compiler inputs stay declared.
Native NSS/NSPR build rules come from pinned
`formatjs/chromium` commit `4a2321d`. GSSAPI headers use the matching pinned
Chromium sysroot archive; product libraries never fall back to host packages.
All 34 PKI sources match the captured BoringSSL target and join its existing
SSL/crypto libraries. Net's shared type headers declare their Mojo tag,
unexportable-key and time-tracker header dependencies explicitly. The tag-only
target exposes one header instead of the complete Mojo header inventory.

```mermaid
flowchart TD
  Sources[Matching patched sources] --> Net[Chromium networking]
  Protoc[Matching native protoc] --> Proto[Original protocol generators]
  Tools[Native root-store and HSTS tools] --> Data[Root-store / HSTS data]
  Grit[Original GRIT and resource ID generators] --> Resources[Resource headers / packs]
  Proto --> Net
  Data --> Net
  Resources --> Net
  NSS[Native NSS / NSPR] --> Net
  Net --> Mojo[Mojo core / platform / embedder]
  IPCz[Matching IPCz] --> Mojo
  Mojo --> Electron[Electron / content]
```

Python generators retain explicit inputs, execution-platform tools, empty child
`PATH` and byte equality across changed paths/mtimes. Two owned GRIT adaptations
make `.pak.info` source paths and the resource-ID header comment relative.
`native_compat_patches.json` records them; parent Chromium files stay unchanged.

NSS module `.chk` files use original DSA-2048 parameters, a public build key and
[RFC 6979](https://www.rfc-editor.org/rfc/rfc6979#section-3.2) SHA-256 nonces.
Original source-built NSS performs key construction, signing and verification;
its random blinding stays enabled. Each integrity action compares output bytes
across paths/mtimes. Public-key metadata inside `.chk` serves module integrity;
release signing has its own interface. Runtime random generation remains original.
Published DSA-2048/SHA-256 vectors check nonce generation.

The runtime probe loads the declared NSS implementation and calls its original
`BLAPI_SHVerifyFile` vector entry. It accepts generated and relocated integrity
files, then rejects changed library bytes and changed signature bytes. HSTS
lookup checks both sides of Chromium's 70-day build-age boundary with a scoped
test clock; production clock and expiry policy remain unchanged.

The runtime probe covers generated suffix/HSTS data, IDNA canonicalization,
invalid URLs, hashing, NSS random generation and Chromium SQL. Mojo checks binary
messages, empty/closed pipes, data pipes, shared mappings and cleanup.
[122f977 components](https://formatjs.buildbuddy.io/invocation/c4852e98-f478-4d62-9b46-d8e782e1ff68),
[consumer](https://formatjs.buildbuddy.io/invocation/376c61c9-c0a3-471b-b9a7-2d07d498f510)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/2b651fc7-4805-4297-8279-0e494a51e15f)
checks passed, including the nonce vectors and fresh network-denial gate. This
full profile remains Linux AMD64. Typed bindings follow below; Blink/content
and the full Electron executable remain unfinished.


## Typed Mojo bindings

`electron_mojo_sources` adds 214 captured C++ units, 29 original Python actions
and four literal GN metadata targets. The actions produce 694 declared files:
parsed Mojom modules, precompiled templates, type mappings, message IDs and C++
bindings. Original response files, build metadata and typemap configurations
remain declared inputs. Every generator compares bytes across changed paths and
mtimes with an empty child `PATH`.

The roots are Mojo C++ bindings, Mojo base types and service-manager interfaces.
Existing native Base, IPCz, networking and compression stay shared. The 345
original Mojo headers reuse the network repository's file identity; they are
not projected again. Both captures use the same native compiler-settings helper;
recapturing networking preserves its profile bytes.

```mermaid
flowchart TD
  IDL[Original Mojom and typemaps] --> Parser[Original parser]
  Templates[Original templates] --> Precompile[Template precompiler]
  Parser --> Generator[Original C++ generator]
  Precompile --> Generator
  Generator --> Bindings[Native typed bindings]
  Bindings --> IPC[Mojo core / IPCz]
  IPC --> Child[Native child process]
```

`//source:mojo_test` launches itself through Chromium's platform channel and
Mojo invitations. It checks a 65,537-byte binary message, a transferred shared
buffer with cross-process coherence, generated `InterfaceProvider` dispatch,
embedded-NUL strings, a transferred reply pipe, clean child exit and malformed
message rejection. It also checks message/data pipes and invalid-handle errors.
No replacement transport or generated-code stubs participate.

[8261fc4 components](https://formatjs.buildbuddy.io/invocation/7616e6df-a464-4d31-9870-8675906e3d6c),
[consumer](https://formatjs.buildbuddy.io/invocation/9a5dbde4-c22d-47b1-a9b9-c86ec8564d44)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/a503d8d2-6a4a-466c-82c0-7c78eb528c8d)
checks passed. This complete typed profile and runtime probe remain Linux AMD64;
the cross-compile check covers existing platform probes, not complete typed
bindings on every target. Full Electron linking remains unfinished.


## Native font and XML dependencies

`electron_fonts_sources` builds all 142 C/C++ units in the captured FreeType,
HarfBuzz, libpng and libxml roots. Five native library/group targets retain
original compiler settings, Chromium's FreeType modules/options, included C
implementation files and source/public headers. Existing ICU and zlib remain
shared. FreeType and HarfBuzz use exact Chromium DEPS commits and checksum-pinned
GitHub archives. All 959 external source inputs match the original Gitiles
checkout bytes; Gitiles archives themselves changed compressed bytes between
fetches and are not used as pinned downloads.

```mermaid
flowchart TD
  Font[Declared font bytes] --> HarfBuzz[Native HarfBuzz shaping]
  ICU[Matching ICU] --> HarfBuzz
  HarfBuzz --> Glyph[Glyph IDs / positions]
  Glyph --> FreeType[Native FreeType rasterization]
  Font --> FreeType
  PNG[Native libpng] --> FreeType
  Zlib[Shared zlib] --> PNG
  XML[Native libxml] --> Content[Skia / content dependencies]
  FreeType --> Content
```

`//source:fonts_test` checks original HarfBuzz fixture advances for `ffi` with
ligatures enabled and disabled, then rasterizes the shaped ligature with
FreeType and checks nonempty pixels. It also rejects invalid font bytes, checks
a two-by-two RGBA PNG memory roundtrip (including alpha), rejects an invalid PNG
signature, parses UTF-8 XML/entity content, evaluates XPath and rejects malformed
XML. ICU data and the 6,404-byte original font fixture are declared runfiles;
no host font lookup participates.

[854f6a7 components](https://formatjs.buildbuddy.io/invocation/de381a35-b6b8-46cf-b868-6f1b830dc130),
[consumer](https://formatjs.buildbuddy.io/invocation/be89e67e-3a77-4364-917e-c8cd913427de)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/cac878c2-42ac-4798-a252-b1fae8de5225)
checks passed. These complete dependency roots remain Linux AMD64. Fontconfig
and Rust fontations follow below. Complete Skia, Blink/content and Electron
linking remain unfinished; existing cross probes do not establish complete
rendering support on every target.


## Fontconfig and Rust fontations

The native font closure now includes all 29 captured Fontconfig C units, with
its original `ENABLE_FONTATIONS` setting and native BCR `libuuid` 2.41.2.bcr.1.
Fontconfig source uses DEPS commit `f0ed9c3f43161d3555f6f7a5234b22fe7ca60727`
and a SHA-256-pinned archive. The full native font/XML closure totals 171 units.

The existing Rust profile adds nine library/proc-macro targets and one original
libc build script. It now has 95 targets from 71 vendored packages. All previous
85 Rust records and previous font-library records remain unchanged. Native
bindgen generates the two original C-header boundaries; Chromium's original
`build/rust/bindings.rs` namespace wrapper stays in use. Binding filters and
C parsing settings retain the original Fontconfig configuration. The capture
records and checks its `BUILD.gn` source hash, including the bindgen-only
visibility, threading and flexible-array settings. Pinned Rust tools and the
existing allocator/prelude remain shared; Cargo never resolves dependencies.

```mermaid
flowchart TD
  Headers[Original Fontconfig C headers] --> Bindgen[Native pinned bindgen]
  Bindgen --> Wrapper[Original Rust bindings wrapper]
  Wrapper --> Fontations[Original Rust fontations / skrifa / read-fonts]
  Font[Declared font bytes] --> Scan[Original Fontconfig C scanner]
  Scan --> Fontations
  Fontations --> Pattern[Native font patterns / charset / matching]
```

The native probe selects Fontconfig's original fontations scanner through
`FC_FONTATIONS=1`. An explicit empty configuration starts without system fonts,
loads only the declared font, checks its family, file identity and character
coverage, then matches it through the native C API. A malformed font file must
be rejected without changing the inventory; clearing application fonts must
leave it empty. The earlier shaping/raster/PNG/XML probes remain included.

[6652729 components](https://formatjs.buildbuddy.io/invocation/3a1191a5-391b-4f00-b679-ceee2aaf82f0),
[consumer](https://formatjs.buildbuddy.io/invocation/d79263f3-c960-4981-acad-338cd9b5d328)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/497602af-9588-4fa5-80e6-2ba8096d5835)
checks passed. Metadata action audit found no CMake or foreign-cc actions.
This complete source profile remains Linux AMD64; full Skia, Blink/content,
other full source profiles and Electron linking remain unfinished.


## JPEG, WebP, GIF and native NASM

`electron_codecs_sources` translates all 213 C units in the captured JPEG, WebP
and Wuffs GIF roots. JPEG keeps its 27 original SIMD assembly runs and original
NASM 2.17rc0, built from all 81 captured tool C units on the execution platform.
The profile contains 26 library/group/tool targets plus the original foreach
action. Every assembly run retains `--reproducible` and compares object bytes
across changed paths and input mtimes. Original included C files, source/public
headers, SIMD inputs, compiler flags and dependency edges remain declared.

JPEG and NASM use exact Chromium fork commits `e14cbfaa85529d47f9f55b0f104a579c1061f9ad`
and `e2c93c34982b286b27ce8b56dd7159e0b90869a2` through pinned Git fetches.
WebP and Wuffs use exact DEPS commits with checksum-pinned GitHub archives.
No host NASM lookup, CMake or foreign-cc action participates. The product archive
aggregate excludes a second target-platform NASM build; assembly actions request
the tool through the execution configuration.

```mermaid
flowchart TD
  Nasm[Matching NASM sources] --> Tool[Native execution-platform NASM]
  Assembly[Original JPEG assembly] --> Objects[27 original SIMD objects]
  Tool --> Objects
  Objects --> JPEG[Native JPEG]
  JpegC[Original JPEG C] --> JPEG
  WebpC[Original WebP C] --> WebP[Native WebP]
  WuffsC[Original configured Wuffs C] --> GIF[Native GIF decoder]
  JPEG --> Skia[Skia dependency closure]
  WebP --> Skia
  GIF --> Skia
```

The runtime probe requires JPEG SIMD dispatch and checks a real 32-by-32 RGB
encode/decode against bounded lossy color error. WebP checks exact lossless RGBA
bytes, including alpha, and invalid-stream rejection. Wuffs decodes an opaque
one-pixel GIF through its original image/frame/pixel APIs, checks the pixel and
end-of-animation result, then rejects a changed signature. Original native codec
implementations perform every operation.

[a4c1c6a components](https://formatjs.buildbuddy.io/invocation/ac78fd37-9f01-475d-8bb5-449482a50752),
[consumer](https://formatjs.buildbuddy.io/invocation/3539d526-2758-4b59-8fc0-06b5fc20d11f)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/534b1402-47d9-4822-b0a5-c9f02074a26d)
checks passed. This full codec profile remains Linux AMD64; the cross check
covers existing platform probes. Complete Skia, Blink/content, other full source
profiles and the Electron executable remain unfinished.


## Complete matching Skia closure

`electron_skia_sources` translates the complete captured `//skia:skia` closure:
1,158 C++ units in 27 library/group targets and 15 original Python actions with
25 declared outputs. Existing Base, fonts, codecs, ICU, compression and tracing
stay shared. Skia, Dawn and Vulkan headers use exact DEPS revisions with SHA-256
archive pins. Native BCR Expat supplies the captured system-library dependency;
X11/XCB/GL/EGL headers come from the already pinned matching Chromium sysroot.
No CMake or foreign-cc actions participate.

The shared Rust profile adds 12 targets, including original PNG/fontations
bridges and a crc32fast build script. It now has 107 targets from 80 vendored
packages. All previous 95 Rust target records remain unchanged. Native CXX
uses the existing pinned executable and target-compiler configuration; original
Rust and C++ bridge sources remain intact.

```mermaid
flowchart TD
  JSON[Original Dawn JSON / templates] --> Generators[Original declared Python generators]
  Generators --> Headers[Dawn / GPU headers]
  Rust[Original PNG / fontations Rust] --> CXX[Native CXX bridges]
  CXX --> Skia[Matching native Skia]
  Headers --> Skia
  Fonts[Native fonts / codecs / shared Base] --> Skia
  Skia --> Probe[Raster / SkSL / Rust codec and font probes]
  Skia --> Content[Remaining content / Electron closure]
```

Generators retain empty child `PATH`, declared files/tools and byte equality
across changed paths and mtimes. Dawn's expected-output lists derive from its
captured extractor outputs, matching the original `generator_lib.gni` declaration;
source hashes record that derivation. Original output-list validation stays
active. `gpu/webgpu/DAWN_VERSION` is a declared 40-byte pinned Dawn revision,
so archive builds do not depend on a checkout hook or ambient Git execution.

PartitionAlloc's `raw_ptr` provider now exports its complete original pointer
header family and transitive includes: 62 headers, with existing allocator code
and configuration unchanged. Wuffs exports its original `src/release/c` public
include directory. Consumers use these shared providers rather than copied
headers or replacement APIs.

The runtime probe checks every pixel of a rasterized SkSL shader and rejects an
invalid shader. Original Rust PNG encoding/decoding must preserve RGBA bytes and
alpha, then reject invalid input. Original Skia fontations loads the declared
font, maps a glyph and returns a nonempty path through its Rust/CXX path bridge;
invalid font bytes must fail. ICU and font data remain declared runfiles.

[3d7a5d1 components](https://formatjs.buildbuddy.io/invocation/3c7c227a-8327-422d-8c40-7509a4ff575f),
[consumer](https://formatjs.buildbuddy.io/invocation/eb13ad3b-8467-451d-8ff5-41aaafca7a66)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/dc1a8ae4-65ef-4469-ae39-52f89c00efd8)
checks passed. This complete Skia profile remains Linux AMD64; runtime coverage
uses CPU raster/SkSL, not a hardware GPU context. Existing cross probes do not
establish complete Skia support on other targets. Blink/content, other full
source profiles and the Electron executable remain unfinished.

## Native graphics closure

`electron_gfx_sources` captures `ui/gfx`, image codecs, memory buffers, data packs
and geometry/range Mojo bindings. It adds 351 native C/C++/assembly units in
62 library/group targets, 34 original Python actions and four literal GN metadata
targets. Existing Skia, Mojo, fonts, codecs and Base providers stay shared.

libdrm and libsync use exact Chromium DEPS commits. Crashpad comes from the
Electron-patched Chromium tree. The original libdrm configuration group retains
its native dependency; no system library discovery or wrapper build substitutes
for these sources. Original generators retain declared inputs, empty child PATH
and changed-path/mtime byte checks.

```mermaid
flowchart TD
  Shared[Native Skia / Mojo / fonts / Base] --> Gfx[Original ui/gfx closure]
  Native[Native libdrm / libsync / patched Crashpad] --> Gfx
  Metadata[Original generators / GN metadata] --> Gfx
  Gfx --> Probe[Geometry / wire types / PNG / buffers / data packs]
  Gfx --> Content[Remaining content / Electron closure]
```

`gfx_test` covers transform composition/inversion, singular rejection, native
geometry/range wire roundtrips and truncated wire rejection, PNG RGBA/alpha and
invalid input, NV12 layout and size overflow, original DRM format/modifier names,
and deterministic binary data packs with duplicate resources and truncated-input
rejection. This captured profile remains Linux AMD64. Hardware GPU/device and
Crashpad process execution need separate runtime coverage.

Recapture from matching public checkouts:

```sh
python3 tools/capture_gfx.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --chromium-root=/path/to/electron-patched-chromium \
  --libdrm-root=/path/to/libdrm-ad78bb591d02162d3b90890aa4d0a238b2a37cde \
  --libsync-root=/path/to/libsync-f4f4387b6bf2387efbcfd1453af4892e8982faf6 \
  --profiles=bcr/overlay/source/native \
  --output=bcr/overlay/source/native/gfx_inputs.json
```

[8f46f43 components](https://formatjs.buildbuddy.io/invocation/064306e7-598c-4ec4-9fb2-1e55f172e442),
[consumer](https://formatjs.buildbuddy.io/invocation/e3112348-39f6-47a5-8001-f72d63c0f457)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/e1c6f98a-f21f-430b-9a5e-2b1206b25deb)
checks passed, including the real gfx runtime probe. Original cc component
headers and Crashpad's assembly include are declared source inputs. Skia
recapture remains byte-identical after sharing the profile ownership loader.
Action analysis found no CMake or foreign-cc actions. Full Electron remains
unlinked; existing cross probes cover their named platform boundaries.

## Native display closure

`electron_display_sources` translates the complete captured `ui/display:display`
and `ui/display/mojom:mojom` roots: 118 native units in 22 library/group targets,
21 original Python actions and three literal GN metadata targets. Existing
gfx/Skia/Mojo/Base providers retain their source and target identities. Chromium
provides device event logging, EDID parsing, native display models and the full
display/gfx Mojo traits. No new upstream source revision is introduced.

```mermaid
flowchart TD
  Shared[Native gfx / Skia / Mojo / Base] --> Display[Original display models / utilities]
  Mojo[Original parser / wire generators] --> Wire[Display / gfx wire types]
  Display --> Wire
  Wire --> Probe[Display model / monitor changes / malformed wire checks]
  Display --> Events[Remaining events / content dependencies]
```

`display_test` checks native/logical coordinates, work-area insets after scaling
and relocation, monitor enumeration/change/removal notifications, primary-display
changes and display wire roundtrips. Original ScreenInfos deserialization must
reject empty lists, duplicate IDs and missing selected IDs. Test models use
explicit values; no host display discovery participates. Generator children use
`-s -P` with an explicit environment and `PYTHONHASHSEED=0`: `-I` would ignore
the seed. Empty PATH, disabled user site/current-directory imports and
changed-path/mtime output checks remain active. The shared Mojo projection patches
only parser diagnostic filenames to source-relative paths; compound `EnableIf`
AST nodes retain those names in pickles. Feature evaluation and generated wire
semantics remain original. Physical display/GPU
execution remains separate coverage. Full profiles remain Linux AMD64.

Recapture from the matching Electron-patched Chromium checkout:

```sh
python3 tools/capture_display.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --chromium-root=/path/to/electron-patched-chromium \
  --profiles=bcr/overlay/source/native \
  --output=bcr/overlay/source/native/display_inputs.json
```

[81686a0 components](https://formatjs.buildbuddy.io/invocation/5469ba93-723a-442d-9f7c-1aee47571ecc),
[consumer](https://formatjs.buildbuddy.io/invocation/8c32e657-744a-4257-b51d-53ba5f139a24)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/7c3d5002-aee4-478a-bc66-fb38212ed06e)
checks passed. The display runtime probe and existing source runtime suite passed.
Action analysis found no CMake or foreign-cc actions. Complete Blink/content,
other full source profiles and the Electron executable remain unfinished.

## Native events closure

`electron_events_sources` captures the complete `ui/events:events` dependency
closure: 417 native units in 125 library/group targets, 76 original Python
actions, seven literal GN metadata targets and one original protocol-copy step.
Existing display/gfx/Skia/Mojo/Base/Perfetto/Protobuf providers retain their
identities. Matching Snappy comes from its exact Chromium DEPS commit; the
existing pinned JavaScript protoc plugin remains an execution tool.

```mermaid
flowchart TD
  Shared[Native display / gfx / Mojo / Base] --> Events[Original UI events]
  Proto[Original protoc / plugins / tracing generators] --> Events
  Protocol[Original X11 protocol copies] --> Events
  XCB[Native XCB / XKB] --> Events
  Events --> Probe[Input / keyboard state / X11 wire / compression probes]
  Events --> Content[Remaining UI / content / Electron closure]
```

Native XCB uses pinned BCR libxcb/xcb-proto sources with declared Python
generation and byte checks across changed paths/mtimes. Original shell moves
and header copies become declared copy actions. Linux abstract sockets stay
enabled, matching the Chromium reference. Native libxau and xkbcommon retain
their BCR source rules; no CMake/foreign-cc wrappers participate.

The runtime probe uses explicit input events, an inline XKB keymap with default
includes/environment names disabled, a fixed X11 keyboard packet and binary
Snappy data. It checks modifier/clone and transform behavior, shift press/release,
invalid keyboard layout rejection, original X11 decoding, XCB display parsing
and compression/truncation handling. No host keyboard layout or X server is
required. This complete source profile remains Linux AMD64; physical X11/device
execution and other full source profiles need separate coverage.

Recapture from matching public source checkouts:

```sh
python3 tools/capture_events.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --chromium-root=/path/to/electron-patched-chromium \
  --snappy-root=/path/to/snappy-32ded457c0b1fe78ceb8397632c416568d6714a0 \
  --protobuf-javascript-root=/path/to/protobuf-javascript-e6d763860001ba1a76a63adcff5efb12b1c96024 \
  --perfetto-root=/path/to/electron-patched-perfetto \
  --profiles=bcr/overlay/source/native \
  --output=bcr/overlay/source/native/events_inputs.json
```

[decd4f5 components](https://formatjs.buildbuddy.io/invocation/69a9e5a2-7f52-4b5e-9019-e668a8c35dd3),
[consumer](https://formatjs.buildbuddy.io/invocation/eafe398a-4731-4923-94ce-1b34ab04fa1f)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/93ec6252-8c42-4cef-9b6d-50def569b0e3)
checks passed. Original X11 keysym headers and three textually included keyboard
C implementations are declared inputs. The wire probe uses public decoding and
owned-memory interfaces. Generator byte checks remain enabled. Complete
Blink/content, other full source profiles and the Electron executable remain
unfinished.

## Native UI and WebUI closure

`electron_ui_sources` captures the complete `ui/base:base` dependency closure:
96 native units in 76 library/group targets, 339 original Python actions,
24 literal GN metadata targets and 15 original copy steps. Existing native
events/display/gfx/Skia/Mojo/Base providers retain their identities. Original
TypeScript, ESLint, preprocessing, minification and GRIT producers remain in the
action graph; explicit ordering dependencies retain validator steps.

```mermaid
flowchart TD
  Pins[Exact DEPS Node / prepatched npm archive] --> Tools[Declared execution tools / source groups]
  Tools --> WebUI[Original typecheck / lint / minify / resource producers]
  WebUI --> Packs[Original WebUI and locale packs]
  Native[Original ui/base / color code] --> Probe[Resource relocation / locale reload / color pipeline]
  Packs --> Probe
  WebUI --> JS[Real generated module semantics]
  Native --> Electron[Remaining content / Electron closure]
```

Chromium's DEPS supplies checksum/generation-pinned WebUI tool sources and Node
22.11.0 for execution. This bootstrap is separate from Electron's Node 22.20.0
webpack toolchain and embedded target Node. No package install hooks run. Shared
canonical source groups retain each declared npm file without repeating npm
file lists in each action. Directory-based tools receive generated outputs and
source inputs from their original GN predecessor actions. TypeScript dependency
configurations retain their original declaration files. GRD manifest inputs
also declare the original static HTML, SVG, font and third-party resource bytes.
Captures reproduce across Python hash seeds. Child PATH remains empty; original
generators retain changed-path/mtime byte equality.

The native probe relocates actual English/French packs, selects each locale with
an explicit `LANGUAGE` value for Linux GLib, reloads locale strings,
compares packed WebUI module bytes with original minifier output and checks
layered native color aliases/postprocessing. A separate probe executes the real
compiled/minified color module with the pinned Node tool, including invalid-input
handling. Full source profiles remain Linux AMD64; complete Blink/content and
the Electron executable remain unfinished.

[2b46400 components](https://formatjs.buildbuddy.io/invocation/589e4e60-43b7-410f-b0c4-afd40ab9c125),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/c1ddb72f-d5fb-446f-8cb4-ea7e8e39da31)
and [cross-compile](https://formatjs.buildbuddy.io/invocation/5dfdee24-4f76-42b3-94ef-77682b793feb)
checks passed. No CMake/foreign-cc actions matched the UI
action audit. The public tool archive is consumed as pinned sources without
package installation or host Node discovery.

Reproduce source capture with the matching patched Chromium tree and extracted
DEPS npm source archive:

```sh
python3 tools/capture_ui.py \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --chromium-root=/path/to/electron-patched-chromium \
  --node-modules-root=/path/to/pinned-node_modules \
  --profiles=bcr/overlay/source/native \
  --output=bcr/overlay/source/native/ui_inputs.json
```

## Native Ozone/GL integration

The validated `e677b62` Ozone/GL baseline contains:
2,147 native units in 306 library/group/runtime targets, 116 original generator
targets (117 runs), eight GN metadata targets and two literal Dawn output lists.
Fifteen source repositories retain the exact Chromium/Dawn DEPS revisions.
Existing native UI, Skia, Mojo, Rust and Base providers retain their identities.

```mermaid
flowchart TD
  Declarations[Captured GN sources / flags / output declarations] --> Native[Native C/C++/Rust rules]
  Declarations --> Generators[Original Python / Wayland scanner / trie tools]
  Generators --> Native
  Native --> Runtime[ANGLE / SwiftShader / Vulkan / Ozone]
  SDK[Pinned Linux SDK / desktop ABI runtime] --> Runtime
  Runtime --> Probe[Explicit SwiftShader / framebuffer readback]
  Runtime --> Electron[Remaining compositor / content / Electron closure]
```

Shared-library version scripts, SONAMEs and ICD manifests remain declared
products. C/assembly members of shared targets link eagerly, matching their C++
objects. The Vulkan loader is entirely C; lazy archive groups discarded its API
exports. A real loader export/dispatch test reproduces that failure before the
link fix. Header providers forward compilation context without adding code to
unrelated DSOs. Rust FFI crates depend directly on their native C++ owners.

Native GLib, GObject, GModule, GIO and zlib have shared outputs with their original
SONAMEs. This gives their initialization and allocator state one owner across
EGL/GLES libraries and the consumer. Desktop ABI data remains 53 declared files
from 49 checksum-pinned Debian packages matching the Chromium SDK; the native
outputs take priority over the five corresponding SDK files. These SDK inputs
are not source-built library claims.

Native Rust providers supply standard-library inputs instead of GN's relative
archive paths. The Wayland scanner consumes Chromium's checked-in Linux
configuration header. Compilation headers stay independent of generated protocol
headers. Original generator validators and changed-path/mtime byte checks remain
enabled, including Dawn's expected-output declarations. The native trie generator
keeps its original C++ executable provider, with ICU data beside its binary in
the execution configuration. PCIutils, Wayland, ANGLE, SwiftShader and the Vulkan
loader compile from source. Execution Node and Electron's embedded Node remain
separate.

The graphics probe loads the actual Vulkan/EGL/GLES libraries, checks the loader
API, explicitly selects SwiftShader, renders a 2×2 framebuffer and checks every
RGBA byte. Loader paths contain declared source/runtime files; optional Vulkan
layers are disabled and caches use test scratch space. Graphics runs first in
source CI; the complete aggregate and suite remain required afterward.

[e42592d components](https://formatjs.buildbuddy.io/invocation/9a591f26-aab9-495f-8a05-da63df40d687),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/44781263-425a-4713-a6e2-288114a29449)
and [cross probes](https://formatjs.buildbuddy.io/invocation/2a544517-a493-4bd2-9e08-ac3beb1bee52)
passed. Temporary crash instrumentation is removed. The clean
[e677b62 components](https://formatjs.buildbuddy.io/invocation/7056db57-2403-44a5-ac43-048b82fa95ec),
[consumer](https://formatjs.buildbuddy.io/invocation/0109ff8b-c8e5-4faf-9cda-c333de0a4be3)
and [cross probes](https://formatjs.buildbuddy.io/invocation/eb37a769-f425-4ba9-9c64-5f77a864c1a2)
also passed.
Source component profiles remain Linux AMD64. Complete Electron remains
unfinished.

Source capture reads metadata only:

```sh
python3 tools/capture_gn_edges.py \
  --gn=/path/to/pinned/gn \
  --chromium-root=/path/to/electron-patched-chromium-and-deps \
  --out-dir=/path/to/configured-gn-output \
  --output=bcr/overlay/source/native/linux_amd64.dependency_kinds.json.gz
python3 tools/capture_platform.py \
  --dependency-kinds=bcr/overlay/source/native/linux_amd64.dependency_kinds.json.gz \
  --graph=bcr/overlay/source/native/linux_amd64.partial.json.gz \
  --chromium-root=/path/to/electron-patched-chromium-and-deps \
  --source-root=third_party/wayland/src=/path/to/wayland-a156431ea66fe67d69c9fbba8a8ad34dabbab81c \
  --source-root=third_party/wayland-protocols/src=/path/to/wayland-protocols-efbc060534be948b63e1f395d69b583eebba3235 \
  --source-root=third_party/wayland-protocols/kde=/path/to/kde-protocols-0b07950714b3a36c9b9f71fc025fc7783e82926e \
  --profiles=bcr/overlay/source/native \
  --output=bcr/overlay/source/native/platform_inputs.json
```

## GPU command-buffer integration

The graphics profile captures GLES2 client/service command buffers, Viz common
and GPU IPC client/host/service: 2,639 native units across 409 library/group/runtime
targets, 179 declared generator targets (180 runs), and 16 exact source pins.
Libyuv comes from its Chromium DEPS revision. GPU/Mojo/Dawn generation and the original
Protobuf wrapper retain their declared tools and outputs.

Chromium's `lastchange_dawn` checkout hook is a declared action. Its original
`lastchange.py` receives pinned Dawn revision/time through its supported environment
interface. A small import-only patch defers depot-tools loading until Git lookup
is needed. The hook runs without Git or clock discovery and keeps its original
header guard and revision format. Capture verifies the original DEPS command;
generated bytes are checked across changed source paths and mtimes.

The native protocol probe uses original command serializers, CommonDecoder,
CommandBufferService and transfer buffers. It checks token/state propagation,
shared-memory byte transfer, invalid ranges/handles, bucket limits and error
callbacks. It also exercises real GPU preference serialization, shader-cache
protobufs, Viz NV12 plane sizing and pinned libyuv ARGB-to-NV12 conversion.
Converted chroma bytes pass through the native transfer buffer and decoder.
GPU preferences use the real source-built Mojo embedder. The existing SwiftShader
pixel probe and complete source suite remain required.

[9a26e4a components](https://formatjs.buildbuddy.io/invocation/85548eee-1919-463f-b3bc-faff67712494),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/7fe6e314-f4e1-48e2-a742-0f55ecf58e30)
and [cross probes](https://formatjs.buildbuddy.io/invocation/2c7580d3-ff97-41a2-a821-cdd4ce646ecb)
passed. The [complete native suite](https://formatjs.buildbuddy.io/invocation/a2205917-022b-4e00-a863-c111dae2b214)
includes the transport and real SwiftShader rendering checks. Full Electron
remains unfinished.

Quoted sibling includes keep their checked-in relative file layout across profile
boundaries. The capture projects their recursive source closure locally instead
of redirecting those files into another source repository. No compiler include
path workaround or source patch is needed.

The GPU transport launcher declares the complete pinned desktop runtime and native
shared GLib/zlib owners. Its isolated library path includes that closure before
host defaults; driver lookup points only to the declared SwiftShader manifest.

## Symphonia media dependency

Chromium's compositor depends on media, including its original Symphonia FLAC
Rust bridge. The capture now includes that exact closure: ten additional Rust
targets and nine vendored packages, preserving the existing 107 Rust targets.
Native rules run the original CXX wrapper with source-built cxxbridge and declared
target Rust configuration. The C++ boundary keeps generated headers separate
from native link owners.

The new native test decodes a complete FLAC packet through Chromium's original
CXX/Rust bridge and compares every output sample against its independent WAV
fixture. Capture verifies the WAV PCM checksum against the FLAC STREAMINFO MD5,
records source SHA-256 values and identifies the first packet by its frame CRC.
The test also checks empty packets, decoder recovery and rejected initialization.
Both fixtures come from the pinned public Chromium sources.

Metadata analysis passed without local build actions; capture bytes remain stable
across hash seeds. [bdd6d7e components](https://formatjs.buildbuddy.io/invocation/86cc1e18-00a5-4033-96eb-cb6f81f7e986),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/b5e0d4f7-7a0e-43a7-9cc1-e93a4dfe85de)
and [cross probes](https://formatjs.buildbuddy.io/invocation/86f8eb41-b3fe-4e20-8731-d765a70eced7)
passed. The [complete native suite](https://formatjs.buildbuddy.io/invocation/0bb1fe8e-7bab-42eb-9eee-a3d994fa6a60)
reports Symphonia, GPU transport and SwiftShader probes as PASSED. Original CXX
generation retains its Python helper imports and checks output bytes across
changed source paths and mtimes.

This dependency remains Linux AMD64. It does not complete the compositor, media
stack or Electron executable; cross probes cover their existing contracts.

The remaining compositor closure includes media codecs, WebRTC and their original
generators. The pinned Chromium reference already has a native
[media rule implementation](https://github.com/formatjs/chromium/blob/4a2321d1086a36b4bb99ec237a379827b784b0b0/overlays/chromium/bcr/overlay/native/media.bzl)
that can guide those ports. Its Chromium 142.0.7444.59 graph cannot replace
Electron's patched 142.0.7444.52 configuration: recapture Electron flags, source
pins and generated outputs, and verify codec/provider compatibility.

## Full media source closure

The platform profile now includes `//media:media`: 1,529 additional C/C++ units
and 156 original NASM object actions. Combined graphics/GPU/media coverage is
4,324 source/object units across 493 library/group/runtime targets, 203 generator
targets (353 runs) and 27 exact source pins. FFmpeg reuses Electron's patched
source repository. Codec configurations and generated outputs come from the
Electron graph rather than the newer upstream Chromium graph.

Original stub generation and source-built NASM remain declared native Bazel
actions. Capture includes their source/header/assembly input closures and checks
output bytes across source paths and mtimes. GN macro expressions preserve their
spaces as a single compiler argument; libvpx's original allocation limit was
verified in the analyzed compile actions.

The pinned SDK now declares ALSA and Pulse headers. Its stripped ALSA link
interface and checksum-pinned real runtime retain matching symbols, symbol
versions and build identity. The runtime closure now has 54 libraries from 50
packages; these desktop ABI libraries are not source-built library claims.

New BB tests compare native FFmpeg FLAC output against the independent WAV
reference, check the original Chrome AAC/H264 decoder registry, exercise Chromium
audio parameters and check ALSA allocation/version APIs without audio hardware.
A separate ELF test verifies SDK/runtime ABI identity.

[755d607 BCR consumer](https://formatjs.buildbuddy.io/invocation/65b0f31c-7d09-4a0b-93fa-36ad204cd4e2),
[source components](https://formatjs.buildbuddy.io/invocation/459c32ae-27ea-4ac6-bf40-b3908f40ca8d)
and [cross probes](https://formatjs.buildbuddy.io/invocation/bd1165c5-db04-43b3-963e-6359254e6449)
passed. Structured results report media runtime, ALSA ABI, Symphonia, GPU transport
and SwiftShader as PASSED. The BCR source test invocation took 267.192 seconds:
1,778 tracked remote actions, 1,292.109 CPU seconds, 740,192,256 bytes maximum
action peak memory, 1,662,435,292 input bytes and 26,726,385 output bytes. These
are observed incremental CI figures, not a cold-build benchmark.

Analysis of the expanded library graph found no CMake or foreign-cc actions.
This profile remains Linux AMD64. Audio server/device integration, compositor
and full Electron remain unfinished.

## Compositor source closure

The platform profile now includes the original `//cc:cc` closure: 2,017 additional
C/C++ units, including Electron-patched WebRTC and pinned federated-compute/SRTP
sources. Combined coverage is 6,341 source/object units, 1,490 library/group/runtime
targets, 525 generator targets (675 runs) and 30 exact source pins. New generators
retain original field-trial, metrics, permissions-policy and GRIT behavior.
GRIT reuses the existing patched network-owned inputs; WebRTC header generation
does not invoke its clock-dependent expiration-report command.

Five checksum-pinned X11 packages extend the desktop runtime to 59 libraries from
55 packages. Their dynamic symbols, available symbol-version sections and build
identities match the SDK interfaces; the real runtime also supplies executable
sections. Source capture is stable across Python hash seeds. Bazel analysis of
the full library closure and runtime probe passes with zero build actions.

The runtime probe exercises layer ownership, replacement, reparenting, geometry
and opacity, then replays an actual paint record through Skia. It checks every
pixel after clipping, translation and alpha blending, plus restored canvas state.
[4a2bf7d source components](https://formatjs.buildbuddy.io/invocation/76fcec92-d070-4111-bb69-9409ad3645a0),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/e094d365-9ce7-4b46-a66b-d7eb2df6f6ef)
and [cross probes](https://formatjs.buildbuddy.io/invocation/462db483-9fb6-4093-9889-cecbb0577540)
passed. Structured results report compositor, media runtime, ALSA ABI, Symphonia,
GPU transport and SwiftShader as PASSED. Existing 493 library records and 203
generator records remain unchanged. Capture declares file-valued options such as
the field-trial schema; its supported `--year=2025` option fixes the copyright
year without reading the clock. WebRTC uses declared SDK PipeWire/SPA headers.
Audio/display server integration remains untested.

The warm source aggregate took 164.160 seconds with zero tracked remote actions;
the following full source suite took 100.692 seconds, also with zero remote
actions. The BCR source suite took 301.185 seconds with two tracked actions,
4.065 CPU seconds, 356,081,664 bytes maximum action peak memory, 437,200,229 input
bytes and 9,228,165 output bytes. These are incremental CI observations, not
cold-build benchmarks; warm orchestration/cache/download time needs profiling.

This profile remains Linux AMD64; full Electron remains unfinished. The next
Blink platform closure adds 5,989 C/C++ units plus Rust crash/font-format and
CrabbyAVIF prerequisites. Its graph also requires original IDL, USB identifiers,
DevTools overlay and additional Blink generators.

## Blink Rust bridges

The Rust profile now captures Blink's original font-format and mixed-language
crash modules: two additional Rust targets, with all 117 existing records and
89 vendor package inventories unchanged. Original CXX actions use source-built
cxxbridge, declared rustc configuration and Python helpers. Generated headers
forward compilation context separately from native link owners. The crash
callback compiles its original C++ source with original flags and source-set
link semantics.

Seven pinned SFNT fixtures cover plain fonts, COLRv0/COLRv1, variable fonts,
sbix and CBDT/CBLC. Tests call every exported format predicate through CXX and
reject empty/truncated inputs; CFF2 and avar2 currently have negative cases only.
The crash probe calls the original Rust/C++/Rust chain in a child with core dumps
disabled, requiring the original panic message and SIGABRT. Crash reporting is
not covered by that check.

Capture is stable across hash seeds. Analysis of the new libraries/tests passes
with zero build actions. The complete platform/bridge dependency audit found
zero CMake/foreign-cc actions, with 20,791 CppCompile actions as a positive control.
[d158dbb components](https://formatjs.buildbuddy.io/invocation/16dbafe5-cc1e-40b8-961b-0ae8fae9d3bd),
[BCR consumer](https://formatjs.buildbuddy.io/invocation/74320089-9454-4c96-9c7e-23d9a7140085)
and [cross probes](https://formatjs.buildbuddy.io/invocation/136d9125-d6f6-4c63-a668-8e89365933b6)
passed. Structured results explicitly report both new probes as PASSED. The BCR
source suite took 39.841 seconds with 12 tracked remote actions, 2.445 CPU seconds,
395,137,024 bytes maximum action peak memory, 156,105,220 input bytes and
10,663,694 output bytes. These are incremental CI observations.

Full source profiles remain Linux AMD64; CrabbyAVIF, Blink and full Electron
remain unfinished. CrabbyAVIF's dav1d/libyuv bindings will reuse the matching
native source owners already present in the platform profile.

## CrabbyAVIF (validation pending)

The Rust profile includes Chromium's original CrabbyAVIF decoder and its dav1d/
libyuv namespace wrappers: 122 Rust targets, with all 119 earlier records and
89 vendor inventories unchanged. Source revision
`3ba05863e84fd3acb4f4af2b4545221b317a2e55` comes from Electron's Chromium DEPS.
Original features, bindgen allowlists and named generated files are retained;
Cargo build scripts are not substituted for the GN graph. Native codec symbols
and headers use the existing matching source-built dav1d/libyuv owners.

The decoder probe compares every RGB byte of the upstream lossless AVIF fixture
against its independent PNG, decoded with the existing source libpng owner.
It also checks malformed input, native codec versions, C API object lifetimes
and limited-range RGB/YUV conversion. Both fixtures have checked-in source hashes.

Analysis passes with zero build actions. Capture is stable across hash seeds.
A full source-aggregate/decoder dependency audit found zero CMake/foreign-cc
actions, with 24,493 CppCompile actions as a positive control. Hosted compilation
and runtime validation remain pending. Full source profiles remain Linux AMD64;
Blink and full Electron remain unfinished.

## CrabbyAVIF decoder

`@electron//source/crabbyavif:crabbyavif` links the original Chromium DEPS
revision through native Bazel Rust, bindgen, dav1d and libyuv targets. The
122-target Rust capture preserves all previous 119 records and 89 package
inventories. Bindgen keeps the original generated filenames and public native
configuration; no Cargo build script replaces GN metadata.

`@electron//source/crabbyavif:decode_test` decodes the pinned lossless AVIF and
compares every RGB byte against its independent upstream PNG. It also checks
malformed input, codec versions, owned RGB allocation/free and RGB-to-YUV
conversion. Like Blink, the probe parses and selects frames while the decoder
owns image planes and metadata. The pinned convenience ReadMemory API shallow
copies metadata; destroying its copied image is unsafe and is not validated.

Implementation `4cc896e` passed hosted components, BCR consumer and cross probes.
The BCR source child reports the decode probe PASSED through cleanup and
conversion. These source profiles cover Linux AMD64; this is not a complete
Electron executable or renderer integration.

## Blink generator prerequisites

`@electron_platform_sources//:blink_bindings` builds the original Web IDL
collections/database, testing IDLs and event tables, plus 17 original platform
generators for runtime features, policy declarations, settings, names and color
data. At `3888599`, this pipeline had 551 generator targets and 1,491 native
library/group records. Existing records stay unchanged; the extra group owns testing IDLs.

Color generation uses declared, source-built `@gperf//:gperf` (3.1.bcr.2). The
runner stages that executable explicitly with an empty PATH. Every generator
runs twice under different source paths and mtimes. Inputs and response files
come from the Electron-patched Chromium 142 graph.

The source aggregate builds these outputs. The source suite includes
`@electron//source/blink_bindings:bindings_test`, checking event inheritance,
component ownership, export metadata and native header directories.

Only generator headers reachable from native C/C++ owners enter the shared
compilation headers. Auxiliary testing IDLs no longer invalidate unrelated
compilation. The selected header set matches the pre-IDL native profile.
Implementation `3888599` passed hosted components, BCR consumer and cross
probes. Its aggregate profile records 26 generator actions, including native
gperf generation, and the full source suite reports the binding probe PASSED.
Full Blink platform integration is unfinished.

## Full Blink platform capture

The Linux AMD64 capture now includes original
`//third_party/blink/renderer/platform:platform` and its dependency closure:
12,256 source/object units, 2,989 native library/group targets, 1,633 generator
targets and three copy targets. Previous native library and literal metadata records remain unchanged.
Resource followups extend GRIT input declarations. Forty-nine exact source pins include the
additional ML/font dependencies; DevTools retains Electron's original patches.

DevTools uses declared Node and the SHA256-pinned esbuild package from its own
DEPS. Its npm inventory contains 24,211 files. FlatBuffers, USB IDs, search-engine
data, Mojo, resources and Unicode character data retain their original producers.
Native character generation receives declared ICU data. The JSON-to-struct CLI
patch exposes a year parameter, and capture pins it to 2025. Source projection
copies patched helpers before applying patches.

`@electron//source/blink_platform:platform_test` exercises native ICU/WTF setup,
UTF-8 validation, grapheme boundaries, string interning, Unicode properties and
generated CSS color lookup. It uses the existing isolated desktop-library
wrapper. Compile, link and runtime validation remain pending. The renderer and
full Electron executable are still unfinished.

GRIT resource inputs include descriptor references, sibling web assets, and all
checked-in layout/scale image variants. The resource fixes remain under hosted
validation.

The generated platform manifest pools repeated string lists. Bazel's exported
`PROFILE` retains its original values; metadata tools use
`tools.native_graph.unpack_profile` when reading the file. A full-data round trip
and comparison of all 76,246 registered action keys verified that pooling alone
preserves build behavior. The compact pooled file is about 26.6 MB instead of
94.7 MB. This measures stored bytes, not build speed.

### Blink core

The Linux AMD64 profile now includes the complete original
`//third_party/blink/renderer/core:core` closure: 36 additional library/group
targets, 3,863 native source/object units and 72 original generators. Source pins
and existing library/action records stay unchanged.

Core-only compilation headers have a separate provider. The base layer retains
its exact 34,134 raw headers and 1,632 generated owners; the core layer adds
3,329 raw headers and 73 generated owners. Both layers derive from the pinned GN
graph, without reading an earlier profile as configuration.

The native core probe uses the original HTML tokenizer for tag case folding,
quoted attributes, named/numeric entities, CRLF normalization, comments, EOF and
incremental input. It uses the declared ICU/runtime closure. Hosted compilation
and runtime validation are pending. Blink modules, content and the full Electron
executable remain unfinished.

Metadata analysis completed with zero build actions. The expanded dependency
audit contains 80,436 actions and 34,342 CppCompile keys; all 30,478 baseline
compile keys remain present. The baseline declared header lists also match
exactly. No CMake/foreign action mnemonics matched this scope.

The [99d6c1d aggregate](https://formatjs.buildbuddy.io/invocation/5cec9852-86d4-45f5-9c19-4a92f51ef3be)
stopped with a Bazel JVM out-of-memory error during compilation. Source-component
and BCR-consumer jobs now request 32 GB workers and set a 24 GB Bazel heap for
every command. Numeric `.memory` profiles accompany the source timing profiles.
Compiler inputs and incremental state settings stay unchanged.

The [5371c2a rerun](https://formatjs.buildbuddy.io/invocation/9e176233-83a0-4b09-bae8-db29253db07e)
failed before compilation when GitHub returned HTTP 504 for `rules_python`.
The larger heap has not yet completed the full graph. Blink core runtime and
the complete Electron executable remain unverified.

CI rewrites only the `rules_python` 1.9.0 release URL to GitHub's corresponding
source tag archive URL, which retains the `.tar.gz` suffix for Bazel extraction
and redirects to codeload. Its SHA-256 is exactly the existing BCR pin,
`098ba13578e796c00c853a2161f382647f32eb9a77099e1c88bc5299333d0d6e`.
The integrity check, module version and BCR patch remain unchanged. This avoids
the failing release endpoint without substituting dependency contents.
The same byte-identical rewrite covers the pinned `bazel_features` 1.50.0
archive after its release endpoint also returned HTTP 504.

The [22ce9da rerun](https://formatjs.buildbuddy.io/invocation/b843727d-5457-4c21-b84b-233a1c1e5829)
passed cross probes but stopped before compilation on a `bazel_skylib` release
HTTP 504. CI now routes its exact 1.9.0 URL to the official Bazel mirror.
The downloaded 44,790-byte archive matches BCR integrity
`sha256-O1tJAGGB9fj/Ym743c6qlem7itKU97XXsR6p992vjFk=`.

The [e03ebb8 rerun](https://formatjs.buildbuddy.io/invocation/6cbe9326-1a21-4aa8-b3c0-40670df0d11a)
passed cross probes but hit HTTP 504 on the rewritten GitHub archive URL too.
CI now prefetches the two byte-identical source archives directly from codeload
into a temporary Bazel `--distdir`, using the original release filenames.
The shell bootstrap checks their pinned SHA-256 values before Bazel independently
checks BCR integrity. Downloads stay outside build actions. No dependency version,
patch, compiler input or source-generation action changes.

The [c2be721 BCR consumer](https://formatjs.buildbuddy.io/invocation/e54b7089-c094-4412-b5d0-1233b2a4d28e)
passed bootstrap fetches, then GitHub returned HTTP 502 for Electron's own source
archive. The prefetch list also includes the exact Electron 39.0.0 archive from
codeload, verified against the existing `bcr/source.json` integrity. Its staged
filename remains `v39.0.0.tar.gz`, matching the BCR URL. This changes transport
only; all source patches and module metadata remain unchanged.

### Blink modules

The Linux AMD64 profile includes the complete original
`//third_party/blink/renderer/modules:modules` closure. It adds 271 library/group
targets, 3,040 native source/object units and 40 original generators. The same
50 source pins remain; existing library, generator, copy, metadata and generated
file records retain their exact values.

Modules have a separate header provider: 1,371 additional raw headers and 41
generated owners. Platform and core header layers remain byte-for-byte equal as
parsed data. These layers derive from the pinned GN graph, without using an old
profile as configuration.

The native modules probe calls the original WebSocket implementation for token
validation, Unicode/control escaping and ordered protocol-header construction.
Hosted compilation, linking and runtime validation remain pending. Content and
the complete Electron executable are still unfinished.

The [168a174 aggregate](https://formatjs.buildbuddy.io/invocation/c517dd1d-417e-430e-9fb0-45d5eeb521cb)
passed the hermetic execution check, then timed out fetching the pinned
protobuf-javascript GitHub archive before the graphics test. Direct codeload
returns the same 400,574 bytes and pinned SHA-256
`dd78fad1311e7819913047f5ee544a384183ae88ca118a22f6d4992d4b2a081b`.
Source archive declarations now try codeload first, with the original GitHub
archive URL as fallback and explicit `tar.gz` extraction type. Original digests,
refs and strip prefixes remain unchanged; release ZIPs and non-GitHub URLs keep
their original routes. CI also checks the URL mapping contract.

The expanded aggregate/modules-probe metadata audit contains 83,962 actions and
37,381 CppCompile keys, with zero CMake/foreign action mnemonics. Across that
scope and the companion core-probe query, all 34,341 current-HEAD baseline compile
keys remain present. This checks action identity, not build speed or runtime
correctness. Earlier audit files predated scoped source-header fixes and are not
the baseline for this comparison.

The first `98d1d70` aggregate stopped while loading the URL-contract test: its
load label pointed inside the development checkout's ignored `bcr/overlay` tree.
The test now loads the helper through the staged `@electron` module, matching
consumer visibility. No build or runtime probe had executed in that failed
aggregate invocation.

### DevTools frontend resources

The Linux profile now captures the complete original
`//third_party/devtools-frontend/src:devtools_frontend_resources` closure: 1,341
producer actions, including 1,340 additions and nine resource groups. Existing
library/generator records and all 50 source pins retain their exact values.
All three native header providers retain the same raw/generated header lists.

Original Node wrappers use the declared Chromium Node executable. Esbuild uses
its existing pinned execution binary; npm inputs come from the exact DevTools
checkout inventory. Builtin-only copy, JSON and tsconfig producers omit npm
source groups. Local script helpers are declared explicitly. Locale collection
also declares its implicit frontend JS/TS/GN scan and i18n helpers, since GN lists
only the collector script and write helper.

The aggregate explicitly requests every frontend producer output. Original GRD
inventory and third-party README assertions remain enabled. Every generator
retains the isolated source-path/mtime reproducibility check. A semantic resource
test checks collected strings from Elements and Network plus the generated
DevTools HTML module entrypoint. Hosted execution remains pending; this does not
package a source-built Electron runtime or establish a build speedup.

Metadata analysis completed with zero build actions. The expanded action audit
contains 86,721 actions; all 37,382 baseline CppCompile keys remain present, with
no additional native compilation keys and no CMake/foreign action mnemonics.
This is an input-stability check, not a runtime or performance result.

The [2b6389c aggregate](https://formatjs.buildbuddy.io/invocation/a5435c31-3830-4c82-8611-1f852d9a670c)
passed bootstrap/URL-contract and graphics tests, then compilation stopped at
`media/gpu/vaapi/vaapi_wrapper.cc:72`: its protected-content header was undeclared.
The profile now declares Chromium's original
`third_party/libva_protected_content/va_protected_content.h` only on
`//media/gpu/vaapi:common`, the captured owner of that source file. No new source
pin, SDK package or compiler option is introduced. A full capture comparison
verified that only this library's header list and the one-file source inventory
addition changed. Hosted compilation still needs to validate the fix.

Aggregate builds and full source/consumer test phases now use `--keep_going`.
Independent targets can finish and populate the remote cache after a compile
failure, exposing more missing declarations in the same run. Any failed target
still fails CI; bootstrap and graphics gates retain their earlier behavior.

### Content Rust libraries

The Linux content graph's additional vendor Rust dependencies form one
`//third_party/rust/llguidance/v1:lib` subtree. Its declaration adds 15 runtime/host
Rust targets and nine vendor package inventories from the same pinned Chromium
source. All 122 existing crate records, 89 package inventories, native bridge
records and bindgen declarations remain unchanged.

The public `@electron_rust_sources//:llguidance` provider combines the original
C header with its Rust library; the aggregate requests the actual root crate
artifact. Platform capture recognizes that original GN root for the future
content import. Original build scripts remain declared Bazel producers with
pinned execution toolchains.

A native C-ABI probe builds an ASCII tokenizer, validates/rejects regex grammars,
checks token masks, consumes a matching sequence, resets and rejects an invalid
token. Hosted compilation, linking and runtime validation remain pending.
Other source profiles and the full content/Electron executable remain unfinished.

Metadata analysis completed with zero build actions. The LLGuidance extension's
86,827-action audit preserves all 37,382 CppCompile, 228 Rustc and 20
CargoBuildScriptRun baseline keys from the VAAPI-fixed graph. Additions include
one C++ probe, 26 Rust compile variants and six build-script run variants. No
CMake/foreign action mnemonics matched. These counts do not prove runtime
correctness or a performance improvement.

The running `c5da231` aggregate exposed a missing shared-storage typemap header.
GN names it in `services/network/public/mojom/BUILD.gn` as `traits_headers`, with
its implementation already owned by
`//services/network/public/mojom:mojom_shared_storage_blink`. The profile now
exports that original header on the same library. Consumers receive it through
their existing native dependencies. Global platform/core/modules header lists
remain unchanged; a fresh capture verified that only the owner's header list
changed. Hosted compilation remains pending.


### Scoped headers and reproducible DevTools workspace metadata

The keep-going source builds exposed missing Chromium headers for ChromeOS
CDM context, credential-manager traits, Viz context-loss/renderer-settings traits
and Blink runtime-feature context. Renderer settings also needs its original
overlay-strategy trait header.
They now belong to their original captured libraries. Shared header layers,
source pins and compiler options remain unchanged.

DevTools generated its workspace UUID from the temporary action source path.
The native Bazel template action adds an optional source-root argument to the
original generator. Only this producer receives the adapted script and declared
`/src/third_party/devtools-frontend/src/front_end` root. Original UUID namespace,
UUIDv5 algorithm and JSON schema remain intact. Other Node generators retain
their original scripts; the two-run reproducibility guard stays enabled.

The resource test checks the generated root and UUID together. Metadata analysis
passed with zero build actions. Hosted generation, compilation and runtime tests
still need to validate this batch; full source-built Electron remains incomplete.


The preceding `55724c0` consumer run completed 46 source probes, including the
LLGuidance C ABI and DevTools locale/HTML checks. Its full test command still
failed on undeclared headers. The matching aggregate also failed its workspace
reproducibility check. These positive probes do not establish a linked Electron
executable or validate this follow-up batch.


The follow-up source-components/source-tests action audit contains 86,748
configured actions, including 37,380 CppCompile and 254 Rustc actions, with zero
CMake/foreign action mnemonics. Analysis executed zero actions. The captured
profile comparison limits changes to five libraries' header lists, five added
raw files and the workspace producer; all other previous sections match.


### Content version metadata

Content needs Chromium's original Git revision header. The profile now captures
`//build/util:chromium_git_revision` and runs its original `build/util/version.py`
with the captured GN arguments and checked-in `LASTCHANGE.dummy`. This preserves
the non-official profile; no host Git metadata, date or environment is consulted.
The existing native network provider still owns version-info generation.

The source aggregate requests the new producer. A source integration test checks
both generated headers against the pinned VERSION, BRANDING and revision inputs,
including GN's revision truncation and non-official build flag. Existing native
libraries, generator records and shared header layers remain unchanged. Hosted
execution is pending; full content and the Electron executable remain unfinished.


Metadata analysis passed with zero build actions. The 86,750-action aggregate
and source-test audit preserves all 37,380 CppCompile, 254 Rustc and 26
CargoBuildScriptRun baseline keys exactly. Two actions are added; no CMake or
foreign action mnemonics appear. These are action-graph checks, not a measured
runtime speedup or successful hosted generator execution.


### Executable Python generator plugins

`electron_source_action` accepts `python_tools`: launcher logical paths mapped
to declared Python script inputs. A declared Linux execution tool launches each
plugin with the same pinned interpreter and isolated imports as the generator.
The original script keeps its logical location for sibling imports. Launcher
arguments live only in action scratch space; no shell, shebang interpreter lookup
or host Python is needed. Plugin paths cannot replace declared inputs or outputs.

The bootstrap probe builds a real plugin action and checks its output through
stdin, empty/spaced/Unicode arguments, sibling imports and an empty PATH. The
runner also repeats generation across source paths/mtimes. Malformed launcher
metadata and undeclared/conflicting scripts are rejected. Compilation and tests
run on BB; local validation is metadata-only. Tracing's actual TypeScript plugin
and the remaining content resource closure are not yet wired to this interface.


### Skia checkout hook

The `10c0802` aggregate failed at `components/viz/host/gpu_host_impl.cc:33`:
`skia/ext/skia_commit_hash.h` comes from DEPS's `lastchange_skia` hook, not a
checked-in header. The consumer completed 46 probes, including DevTools workspace
metadata; full Blink/core/modules tests remained blocked by compilation.

The capture now validates the original hook command and runs original
`build/util/lastchange.py` with the pinned Skia commit and its
[committer timestamp](https://github.com/google/skia/commit/f4ed99d2443962782cf5f8b4dd27179f131e7cbe).
No Git checkout, host clock or fabricated header is needed. Only the Viz host
library exports this generated header; shared header layers remain unchanged.
The content metadata test compares the generated macro with the original Skia
source profile. Hosted generation and compilation remain pending.


Combined source/bootstrap metadata analysis passed with zero build actions.
The explicit plugin-fixture dependency audit contains the native launcher and
real generator action, with zero CMake/foreign actions. Its two additional C++
compile variants are target/execution configurations of that launcher; 737 other
C++ keys already exist in the source-component graph. Runtime validation remains
pending on BB.


The `1e954b7` bootstrap built its plugin fixture, then the test failed before
assertions because its sibling import directory was undeclared. The test now
declares that import path. Original protoc canonicalizes plugin executables, so
launchers are private executable copies with adjacent argument metadata; the
fixture now canonicalizes its executable too. Hosted assertions remain pending.


### Content tracing protobuf bindings

The profile now captures original
`//content/browser/resources/traces_internals:config_proto_gen`. Its protoc and
Node inputs retain existing execution providers. The Python plugin uses the
native launcher; original GN arguments remain recorded separately. The compiler
receives Chromium's original ts-proto options and pinned npm inventory.

Perfetto's flattened schema comes from the existing patched Electron source
repository. Its DEPS revision is checked against that repository's upstream pin;
no new source revision or archive is introduced. Existing library/generator
records and shared header-layer inputs match the previous capture.

A declared esbuild action bundles the generated TypeScript with pinned packages.
The Node test checks exact duration-field wire bytes, nested buffer round trips
and malformed input rejection through the actual generated TraceConfig API.
Generation, bundling and runtime validation run on BB; full content resource
closure and the Electron executable remain unfinished.


Metadata analysis completed with zero actions. Against exact `b9b30d8`, the
86,815-action component/plugin/tracing audit preserves all 37,382 CppCompile,
254 Rustc, 26 CargoBuildScriptRun and 6,330 ElectronPython baseline keys. Two
Python producer actions are added; no CMake/foreign actions appear. This checks
cache-key preservation, not a measured runtime speedup. The repaired native
plugin bootstrap passed on BB; tracing generation and runtime checks remain pending.


### Binary protobuf resource policies

The content resource closure now includes original Safe Browsing file-type and
SSL error-assistant writers, their generated C++/Python bindings and protobuf's
GN-listed Python runtime copies. Writers keep original arguments, including
isolated Python re-execution, with the pure Python protobuf implementation
explicitly selected. No host protobuf package or pip step is used.

The two generated-only native libraries export their own generated headers.
Capture rejects new raw native sources on those scoped libraries. Their parent
source directories and generated headers do not expand shared Blink header
layers; existing library/generator records remain unchanged.

The resource test checks declared runtime provenance, Linux-specific/any/default
file-type settings and policy identities. The SSL payload must decode to the
entire declared source policy. These use actual generated bindings and runtime;
hosted generation, native compilation and runtime assertions remain pending.


### Blink ICU runfile paths

The `b9b30d8` consumer passed source metadata and plugin checks. All three full
Blink probes linked, then failed `pinned ICU data opens`. Their declared ICU
rootpath contains a parent component; Chromium `base::File::Initialize` rejects
such paths before any OS open. The shared test wrapper now canonicalizes only
trailing declared data files. Its DLL/driver search layout stays intact.
The existing three native probes remain the regression loop; hosted runtime
validation of this path fix is pending. No native assertions were removed.


The `b9b30d8` [source aggregate build](https://formatjs.buildbuddy.io/invocation/4e5c3e23-b304-4378-bdec-1982df289d60)
completed successfully on BB in 1,545.062 seconds. Its subsequent full test phase
failed only the three Blink ICU-open checks in the captured probe summaries.
This proves the imported component aggregate, not a linked Electron executable
or complete content resource closure.

Final resource metadata analysis executed zero actions. The 86,856-action audit
preserves all 37,382 CppCompile, 254 Rustc, 26 CargoBuildScriptRun and 6,332
ElectronPython baseline keys. Additions include two native protobuf compilations
and six generator/copy actions. No CMake/foreign actions appear; hosted execution
of these resource additions and the canonical ICU path fix remains pending.


### Content Mojo and DevTools web assets

The capture adds the original Mojo-lite concatenation/export replacement and
DevTools compression/GRD producers. The latter retains the complete original
frontend dependency graph, file list, Brotli framing and source hashes. The
source aggregate requests these actual products through public file aliases.
No native libraries or existing producer records change.

Hosted tests evaluate the real concatenated Mojo bundle and exercise signed and
unsigned 64-bit wire helpers. They also decompress the generated DevTools HTML,
check its length header/hash, and verify GRD compressed-resource references.
Local validation remains metadata-only; actual generation and runtime checks
are pending on BB. Full content and the Electron executable remain unfinished.


Metadata analysis passed with zero build actions. The 86,882-action audit keeps
all 37,384 CppCompile, 254 Rustc, 26 CargoBuildScriptRun and 6,338 ElectronPython
baseline keys. Five Python producer actions are added; no CMake/foreign actions
appear. Hosted generation and semantic assertions still need validation.


The `ead6a0f` component build passed in 99.729 seconds. Full Blink platform,
core and modules runtime probes now pass, confirming the ICU path fix. The
binary policy probe also passes with its declared pure Python runtime.

Tracing generation succeeded, but its offline bundle fixture could not resolve
Chromium's rewritten `/@bufbuild/protobuf/wire/index.js` browser import. The
fixture now maps that one import to the pinned npm runtime in a scratch copy.
The original generated product retains its browser URL. The real wire runtime
test remains required; this fixture correction still needs hosted validation.

### Catapult standalone tracing resources

The content closure now declares Catapult's original standalone tracing
HTML/JavaScript producer, all 679 GN-listed inputs and original minification.
The archive follows Chromium's exact DEPS commit and adds SHA-256 verification;
existing source revisions and native library/header layers remain unchanged.
Metadata analysis passed. The 86,900-action audit adds one Python generator,
preserves all previous C++/Rust/Python action keys and finds zero CMake or
foreign-cc actions.

The resource contract check verifies the Chromium `tracing.js` route, flattened
HTML imports, retained viewer entrypoint and JavaScript syntax with pinned Node.
It does not establish browser UI execution. Generation, reproducibility and
contract assertions remain pending on BB; full Electron integration is unfinished.


### Content WebUI resources

A separate source projection captures the original content WebUI closure: 238
Python producers, nine copies and 13 literal metadata targets. It retains all
155 resource entry points, TypeScript compilation, ESLint, original bundles and
GRIT resource generation. Existing UI/platform providers own their outputs;
the capture rejects new native source compilation. Node and npm inputs reuse
the existing pinned Chromium tools.

The existing UI translator accepts an explicit profile and aliases; its default
profile remains unchanged. Content resource generators stage provider outputs
without reopening their implementation inputs. Metadata analysis passed with
zero executed actions. The PAK contract test resolves generated tracing IDs and
compares recovered HTML/JavaScript against the original Catapult products.
The 87,412-action audit preserves every previous C++/Rust/Python action key,
adds 248 Python actions and finds zero CMake or foreign-cc actions.
Generation, reproducibility and contract execution still need hosted BB evidence.
These resource checks do not establish browser UI execution or a linked Electron.


### Hosted tracing wire result and manifest fixture correction

The 71f1e29 BCR consumer completed its source tests. The tracing protobuf wire
runtime, binary policies and all three native Blink probes passed. Its only
reported failed probe was the web-assets test, isolated to the manifest case.
The original DevTools GRD template deliberately gives `COMPRESSED_PROTOCOL_JSON`
no `resource_path`; the fixture incorrectly indexed every include by that key.
It now checks this protocol placeholder separately, including Brotli compression
and resource-map exclusion, before checking the routed frontend assets.
The original generator and asset contracts remain unchanged. Hosted validation
of this fixture correction and the new resource projections is still required.


### Remaining content generator families

The content frontier now requests the original CT log list, domain reliability,
policy templates/source, model descriptors, vector icons, Blink validation,
speech-dispatcher loader and histogram allowlist producers. Their closure adds
14 actions and two groups without native sources. New generated headers remain
scoped to their future native owners; existing native source configurations and
header inventories are preserved.

Policy templates declare every source YAML and the vendored PyYAML runtime.
Model descriptors use the existing GN-listed pure Python protobuf files.
A checked substitution writes policy depfile dependencies relative to the build
directory: the original writer otherwise records its absolute `__file__` root.
The JSON/proto/C++ generation logic stays upstream. Policy tests compare all live
and deleted IDs against source YAML, check the homepage schema and require
relative declared depfile paths. All execution remains pending on BB.

The 7809849 BCR consumer found a Catapult import failure at its entrypoint.
GN's resource inputs omit `tracing_build` and its parser runtime. The capture now
adds that package and the exact BeautifulSoup/html5lib/webencodings/six source
directories selected by Catapult's own `_InitBeautifulSoup`. No replacement
parser, host package or disabled minification is introduced. The existing tracing
asset and PAK contracts remain required. Full Electron integration is unfinished.


The 87,459-action metadata audit passed: 37,384 C++ compile actions, 254 Rust
and 26 Cargo build-script action keys are unchanged. Python actions increase
from 6,592 to 6,606; every previous action key remains present. Zero CMake or
foreign-cc actions matched. This does not replace hosted generator/runtime tests.


### Content SDK link interfaces and runtime packages

A full `//content:content` metadata capture succeeds after resolving two missing
system providers: CUPS and xshmfence. The experiment adds 445 native libraries
and 382 generators without changing existing library records. Those native
targets are not imported or compiled yet; their header layers still need scoping.

Both interfaces come from the existing pinned Chromium SDK. CUPS headers get a
separate owner so existing SDK header consumers stay unchanged. Executable
libraries come from 18 exact Debian packages, including their transitive runtime
closure. All 18 archive SHA-256 hashes and original library MD5 records were
verified against SDK package metadata; ELF dependency lists match the pinned
runtime manifest. No host library lookup supplies these inputs.

The runtime ABI test compares exported symbols, symbol versions and build IDs
between each SDK interface and its executable Debian runtime. It also requires
code in the runtime and no code in the SDK interface. This artifact check does
not establish native CUPS/fence execution or a linked Electron. The 87,475-action audit preserves all previous C++/Rust/Python action keys
and finds zero CMake/foreign-cc actions. Hosted ABI execution remains required.


### Catapult Web Components resource

The 75b2b3b consumer gets past Python imports but fails while loading a tracing
HTML script reference. Sanitized diagnostics identify `webcomponents.js`;
`tracing/ui/base/webcomponentsjs_polyfill.html` references the pinned archive's
`third_party/polymer/components/webcomponentsjs/webcomponents.js`. That resource
is now declared explicitly. Original minification and HTML imports stay enabled.
Hosted generation and resource contracts still need validation.


The same hosted consumer reports `policy_test`, `web_assets_test`,
`tracing_proto_test` and `binary_proto_test` passed. This verifies the original
policy template/depfile contract and corrected DevTools manifest fixture. The
Catapult asset and PAK targets still failed to build before this resource fix.
Combined SDK/resource metadata analysis passed with zero executed actions.


### Full native content closure

The profile now requests the original `//content:content` closure. Capture adds
445 native libraries and 382 producers. Original GN sources, flags, dependencies
and public headers remain attached to their owning libraries. Existing Rust and
PartitionAlloc targets reuse real providers; content WebUI outputs retain their
existing owner. Imported provider aliases back to the platform repository are
excluded while recapturing its own targets.

Content gets a fourth header layer with 7,445 original headers and 384 producer
dependencies. The previous platform, Blink core and Blink modules header layers
and all existing library/action records are identical to the preceding profile.
The capture keeps the pinned QUICHE source root when scanning the network tree.

The aggregate source target requests all new native objects. This is not a linked
content executable or Electron. Local work only inspects metadata; compilation,
generation and tests remain on BB. Action analysis and hosted validation are
still required for this expanded closure.


The expanded metadata graph analyzes successfully with 93,735 actions and zero
CMake/foreign-cc actions. C++ compile actions increase from 37,384 to 41,454;
Rust remains 254 plus 26 Cargo build-script actions. Python actions increase
from 6,606 to 6,991 and all previous Python/Rust keys remain present.

One existing SQLite header becomes platform-owned so new native sources can use
its quoted relative include. This replaces 19,128 existing platform C++ keys;
18,256 other C++ keys remain present. The prior header lists and native library
records are unchanged. This measured rebuild is not a performance improvement;
cache ownership can be narrowed after correctness is verified on BB.

Open Screen and PDFium are fetched at Chromium's exact DEPS revisions. Their
source projections are required by the new closure; Electron-owned source files
continue to use the existing Electron archive anchor. Hosted native compilation
and eventual Electron linkage remain unproven.


### Complete tracing asset inventory

The 0f52db8 consumer passes the new SDK ABI checks and policy test. Catapult gets
past Web Components and reports another undeclared script, `pako.min.js`.
The capture now declares web assets under the original tracing, Polymer and
tracing third-party roots. This covers the project's vendored script search
paths while retaining its upstream parser/minifiers. Large trace-data archives
are outside this inventory. Generation and PAK contracts still need BB evidence.


The combined tracing/native content/SDK metadata check passes after adding all
four repository imports to the development module and matching BCR templates.
No build, generator or test actions ran locally. The tracing asset inventory
changes only Catapult inputs; existing native records and header layers stay
identical to the expanded content profile.


### WebUI provider interfaces and deterministic Rollup configuration

Live source-components diagnostics identify undeclared GRIT images/translations,
missing TypeScript project inputs, an absolute Rollup config root and the vector
icon unit-test template. Capture now stages external producers' output closure
without reopening their implementation scripts. TypeScript providers also expose
source/declaration/config inputs required by project references. GRIT reuses the
existing XML resource scanner for images, scale variants and locale catalogs;
its Brotli argument names the declared local executable explicitly.

Content WebUI capture filters its own inherited provider aliases and discovers
entry points through the native content graph, so recapture works after native
content is imported. Original roots/native records stay unchanged. A checked
Rollup source adapter stores a relative build path and resolves it with Node's
`node:path` during execution. The plugin receives the same absolute input root;
source-action reproducibility verification remains enabled. The icon producer
now declares its original `vector_icons_unittest.h.template`.

These changes address observed BB failures. Static input checks find the reported
images/catalogs, generated frontend compression products and TypeScript provider
declarations. Actual generation and all resource contracts still require BB.


The corrected graph analyzes with 93,736 actions. All 41,454 C++ compile, 254 Rust,
26 Cargo build-script and 6,991 Python action keys from the expanded content
baseline remain present. No CMake/foreign-cc actions matched. This audit verifies
declarations/configuration; hosted execution still must prove the fixes.


### Electron GTK and notification loader targets

The profile now includes Electron's original GTK stubs and libnotify loader.
Their closure contains two source sets, two Python generators and the GTK
configuration group. A fifth header layer owns 386 Electron headers and these
two producers. Existing native records and all four earlier header layers stay
unchanged. The headers come from the original source checkout.

GdkPixbuf uses the same pinned SDK for headers/link interface. Its exact Debian
runtime package is pinned by SHA-256; extracted library bytes match the SDK's
original package metadata. Existing runtime providers cover its ELF dependencies.
The ABI contract now checks GdkPixbuf alongside CUPS and xshmfence. This does not
claim desktop notification execution or Electron linkage; hosted compilation and
ABI checks remain required.

The full `//electron:electron_app` frontier still has 2,078 uncaptured targets
above existing providers, including Electron's native library, crash handling,
resources, snapshot tooling and additional generated APIs. These two native
prerequisites are part of that closure; full executable integration remains open.


The 93,753-action audit adds two C++ compile actions and two Python producers.
All previous C++/Rust/Python action keys remain present; no CMake or foreign-cc
mnemonics matched. Metadata analysis does not establish hosted execution.


### Electron fuse and Node macro generators

The native profile now captures Electron's original fuse and Node macro
generators with their GN arguments and declared inputs. Their outputs retain
the paths consumed by `electron_lib`. Both scripts use the pinned Python
toolchain; neither needs host Python or npm.

A hosted artifact contract compares all four generated files against the
existing Bazel producers: `fuses.h`, `fuses.cc`,
`push_and_undef_node_defines.h` and `pop_node_defines.h`. This also checks the
two Node source projections agree. Execution remains pending; metadata analysis
does not prove byte equality.

The dependency audit has 93,774 actions. All 41,456 C++ compile, 254 Rust,
26 Cargo build-script and 6,993 existing Python action keys remain present;
exactly two captured Python producer keys are added. No CMake or foreign-cc
mnemonics matched. No build, generator or test ran locally. The executable
frontier still has 2,076 uncaptured targets; full Electron linkage remains open.


### Hosted content input failures

At `0f2b70e`, the [BCR consumer](https://formatjs.buildbuddy.io/invocation/d95c2ae9-2364-4e15-a145-bc7d59516f3a)
passed, including Catapult, tracing WebUI, policy, SDK ABI, binary resources,
Blink and DevTools probes. The [components build](https://formatjs.buildbuddy.io/invocation/c69cb285-f229-4804-84ed-8443dd4105fb)
failed on undeclared content headers and security interstitial bundle inputs.

Capture now declares the original raw JavaScript bundle directories. GN's
bundle arguments name those inputs, but its action input list omits them.
Four bundle actions gain inputs; no new WebUI files, native libraries, source
pins or generator bodies change. Rollup and two-run reproducibility stay intact.

The content header layer also exports the original credential-manager traits
and types, reporting JSON keys, Electron file-dialog interface and Puffin
public headers. All come from existing pinned archives. Earlier platform and
Blink header layers retain their exact inventories; content compile inputs
change to cover the missing interfaces. Hosted validation remains required.


The corrected 93,774-action graph passes metadata analysis with zero local
processes and no CMake/foreign-cc mnemonics. It retains 41,456 C++ compile,
254 Rust, 26 Cargo build-script and 6,995 Python actions. The content interface
change replaces 4,072 C++ action keys; the other 37,384 remain present.
Rust and Python keys stay unchanged, though the four bundle actions now declare
additional inputs. Matching action keys alone do not prove cache reuse when
input sets change.


### Original Electron version producers

The native profile captures `electron_version_args`, `electron_version_header`
and `electron_win_rc`. The first invokes the original
`script/generate-version-json.js` through pinned Chromium Node. Its GN version
argument remains `39.0.0`. The other two invoke the original Python template
generator and templates. Output paths match the native Electron consumers.

`capture_node_tools.py` derives the exact semver 7.6.3 archive and SHA-512
integrity from Electron's original package.json/yarn.lock. Capture checks that
closure against the committed inventory. Bazel stages those declared package
files under `electron/node_modules/semver`; npm and install hooks never run.
The npm preflight stamp is not produced: pinned Bazel dependencies and lock
validation replace that installation guard. Original arguments and preflight
label remain in capture provenance. No application generator is replaced.

A hosted artifact contract checks release and beta JSON, C++ version macros and
Windows FILEVERSION/PRODUCTVERSION fields. Its beta fixtures execute the same
original generators with `40.2.1-beta.3`. Both production and fixture actions
retain empty PATH and two-run path/mtime reproducibility checks.

The 93,802-action dependency graph analyzes with zero local processes and no
CMake/foreign-cc mnemonics. All 41,456 C++ compile, 254 Rust and 26 Cargo
build-script keys remain present. Six Python actions are added, three for the
captured producers and three for beta fixtures. Native libraries, header layers,
source pins and existing producer records retain their exact values. Hosted
execution remains required; full executable linkage is still open.


### Notification SDK and nested GRIT inputs

The `f5c3c64` components build exposed missing `libnotify/notify.h` and the
nested DomDistiller include. Its consumer passed the original fuse/Node output
comparison and the SDK ABI contract including GdkPixbuf; full execution remains
pending.

Libnotify 0.7.9-3 development and runtime packages are pinned by SHA-256 from
Debian. Four public headers form a provider used only by Electron's loader.
The original `libnotify.so.4` runtime joins the existing desktop runtime; its
ELF dependencies are already covered. Bazel extracts both Debian payloads with
built-in archive operations. No host dpkg, compiler wrapper or package manager
runs. This does not establish desktop notification behavior.

GRIT capture now follows nested `<include src>` references. The component pack
gains three original JavaScript inputs. DomDistiller dist is pinned to Chromium
DEPS commit `199de96b345ada7c6e7e6ba3d2fa7a6911b8767d`; Readability uses
`1f0ec42686c89a4a1c71789849f7ffde349ab197`. WebUI repositories select those
source roots explicitly. No generated JavaScript is fabricated.

The resource contract reads the actual component DataPack, checks all three
source payloads were inlined, rejects unresolved includes and parses the emitted
JavaScript with pinned Node. It retains the existing tracing payload checks.
Hosted execution remains required.


The final 93,803-action graph analyzes with zero local processes and no
CMake/foreign-cc mnemonics. Only the notification loader C++ key changes; the
other 41,455 C++ keys and every Rust/Cargo/Python key remain present. Existing
native library records and header layers remain unchanged. GRIT's declared
inputs change, so matching Python action keys do not imply cache reuse.


### Full Electron app resources and locale repacks

WebUI capture now starts at `//electron:electron_app`, with an optional root
argument for narrower source audits. It covers 324 roots and 544 actions,
including PDF, print preview, extension resources and Electron's own pack.
The 306 added producers preserve every existing producer record. This profile
continues to reuse native providers; it adds no native implementation sources.
Electron's resource manifest resolves through the pinned Electron source root.

The native profile also imports the original `//electron:packed_resources`
closure: 225 `pak_util.py repack` actions, including 220 locale variants.
Only the repack command is accepted. It uses declared upstream grit Python
files, an empty PATH and existing two-run reproducibility checks. No host
Brotli fallback or replacement pack writer runs. Source components request
these real outputs through `electron_packed_resources`.

That closure includes 18 original generated C++ resource maps and 36 library/
group records. Existing library/action records and the first four header layers
remain unchanged. The Electron layer gains the resource wrappers' headers.
The runtime contract checks the final resources.pak preserves Electron's
discovery-page route and all three inlined DomDistiller/Readability payloads.

The complete dependency audit has 95,196 actions and zero CMake/foreign-cc
mnemonics. It retains 41,454 existing C++ keys, changes the two GTK/notification
keys for the expanded Electron header layer and adds 18 resource-map compiles.
All 254 Rust, 26 Cargo and 7,001 previous Python keys remain present; 534
Python actions are added. Metadata analysis ran zero build/test processes.
Hosted execution remains required; full Electron executable linkage is open.


### Original extension schema and feature compilers

Capture now follows `electron_app` to its 25 original JSON/IDL compiler targets.
Their foreach expansions request 155 generator runs. All use declared schema
inputs plus the original compiler, legacy/modern IDL parser, comment parser and
PLY files. `electron_api_generated` exposes the real products to source builds.
No host Python packages or replacement API compiler are used.

Four copyright helpers read the wall clock. Checked source adapters replace
those year reads with `ELECTRON_SOURCE_COPYRIGHT_YEAR=2025`, declared only on
these compiler actions, matching this source snapshot. Existing actions consume
none of the adapted files. Generator logic and two-run reproducibility checks
remain intact.

The hosted contract compares all 13 generated feature registration tables with
the original JSON keys using Chromium's declared comment parser. It also checks
public provider declarations and the fixed source copyright year. The test
does not import the feature compiler. Execution remains pending.

The 95,526-action dependency audit passes with zero local processes and zero
CMake/foreign-cc mnemonics. All 41,474 C++, 254 Rust, 26 Cargo and 7,535
previous Python action keys remain present; exactly 155 Python actions are added.
Native libraries, header layers, source pins and existing producer records retain
their exact values. Full executable integration remains open.


### GRIT cross-directory assets and Windows-style paths

The `b1c1300` hosted consumer passed release/beta version metadata, original
Electron bundles and native runtime probes. Resource execution exposed missing
neterror images, an extension select image and Chrome/extension feature JSON.
The latter use Windows separators in GRIT file attributes; capture now
normalizes them as GRIT does.

Asset discovery follows HTML source/stylesheet references, CSS URLs/imports and
srcset candidates across source directories. External/runtime URLs are skipped;
only files in pinned source roots enter the action inputs. Eight WebUI actions
gain inputs. Generator records otherwise keep their original bodies and options.
The resource contract checks both original neterror PNG scales survive inlining
into the actual component DataPack.

The 95,526-action graph passes metadata analysis with zero local processes and
no CMake/foreign-cc mnemonics. All 41,474 C++, 254 Rust, 26 Cargo and 7,690
Python action keys remain present. Input sets change, so this does not prove
cache reuse. Hosted resource validation and full Electron linkage remain open.


### Original Electron JS2C invocation and declared GRIT variables

The native profile now invokes Electron's original JS2C Python wrapper with the
source-built Node JS2C tool. Its eight inputs come from existing native webpack
producers. Capture verifies the original configuration, output names, buildflags
and development-mode arguments before assigning those providers. Npm preflight
stamps are not fabricated; pinned package/lock validation remains authoritative.

The producer contract compares the resulting `gen/electron_natives.cc` bytes
with the existing native generator, alongside fuse and Node macro products.
Both execute the real source-built tool. Webpack declaration generation and
typechecking remain unfinished; this provider bridge does not close that gap.

GRIT discovery now reads declared `-E` values for source-tree paths and branding.
Generated-tree variables remain with their generated providers. The final-pack
contract checks the Linux Chromium logo bytes against the original source image.
This covers the newly observed branding/scaled-image input failures.

The 95,528-action dependency audit passes with zero local processes and no
CMake/foreign-cc mnemonics. All 41,474 C++, 254 Rust, 26 Cargo and 7,690
previous Python action keys remain present; one original JS2C invocation is
added. Existing native records, header layers and source pins remain unchanged.
Byte equality and resource contracts still require hosted execution; full
Electron linkage remains open.


### Native Electron library closure

The `8c98695` hosted consumer passed the original Electron JS2C byte comparison
and release/beta version tests. API feature testing failed before assertions:
Bazel tokenized unquoted JSON arguments. The test now quotes each JSON argument.
Original API compilers also need sibling/include-rule schemas and implementation
headers for registration discovery; capture declares those source inputs.

GRIT `<include>` entries read plain files even when their `type` says
`chrome_scaled_image`. Scale-directory discovery now applies only to
`<structure>`. The WebUI profile keeps its 544 generator records and adds the
two missing WebID PNG inputs. The final-pack contract checks both payloads.

The Linux AMD64 profile additionally captures `//electron:electron_lib`:
826 additional library/group targets and the original context snapshot generator,
checksum, Autofill and DomDistiller helpers. Ink, ink-stroke-modeler and
libaddressinput use Chromium DEPS commits with SHA-256-pinned public archives.
Hunspell retains its `.cxx` sources and `.hxx` headers. GN skips Objective-C
sources without Linux tools; capture records those three paths without compiling
them. Nonexistent GN header-only entries remain recorded as provenance.

The GPU lists version header comes from the original checkout hook with pinned
Chromium commit metadata. Compilation receives the missing Ash switches and
enterprise download headers. Shared generated implementation files retain their
existing providers across profile boundaries.

GTK/GDK, cairo-gobject and libatomic use the captured SDK's original Debian
package versions. Runtime binaries match the original package MD5 records in the
SHA-256-pinned SDK; downloaded packages have SHA-256 pins. Static ELF inspection
adds their complete dependency closure: 90 libraries from 86 packages. The ABI
contract now compares seven SDK/runtime pairs. This does not establish GTK data,
theme or plugin behavior.

Native tools isolate synthetic header providers only when they feed their own
header layer. Dependency capture selects 11 library/group targets, rather than
reclassifying the entire 5,235-target execution closure. Other native libraries
keep their existing generated-header providers. Isolated tools receive declared
raw headers and original GN generator dependencies. Country-name generation
receives native ICU data beside its executable; tools share one staging action
for identical data in the same output directory.

Hosted compilation and new contracts remain required. Remaining content C++
constraint failures, webpack typechecking, full executable linkage and all-triple
source runtimes remain open. No local compilation or tests run for this capture.


The complete component/test graph analyzes successfully: 132,653 actions,
including 67,494 C++ compilations, 260 Rust compilations and 8,799 original
Python generator actions. Analysis executes zero build actions. No CMake or
foreign-cc mnemonics appear. Of the prior graph's compile keys, 27,040 C++,
all 254 Rust and all 26 Cargo script keys remain present. Expanded tool/header
contexts change other keys; this is not evidence of warm-cache performance.


### Final executable and original default app

The Linux AMD64 profile now includes `//electron:electron_app`, the sandbox
helper and Crashpad handler. `//source:electron_programs` exposes all three to
the component build; `//source:electron_binary` selects the main executable.
Compilation, linkage and native launch still need hosted evidence.

```mermaid
flowchart LR
  docs[Pinned API docs] --> types[Original declarations and TypeScript smoke]
  types --> javascript[Original default-app TypeScript]
  javascript --> asar[Original gn-asar.js]
  assets[Pinned static files and Octicons] --> asar
  asar --> app[electron_app data dependency]
  native[Native Electron libraries] --> app
```

Default-app actions run the original docs parser, declaration generator,
upstream type smoke suite, TypeScript compiler and ASAR script through declared
Node/Python toolchains. Their 145-package closure comes from the original Yarn
lock, including the versioned DefinitelyTyped Node archive root. Checked source
inventories preserve original GN/npm commands. The version helper reads declared
`override_electron_version` metadata; generator products are compared across two
source paths and input mtimes. Shared npm staging also serves existing bundles.
No install hooks or npm preflight stamps are generated.

The archive contract checks every packaged JS/static/icon file against its
producer, verifies per-file/block SHA-256 and checks module syntax with declared
Node. Declaration generation runs the upstream main/renderer/utility type suite
before publishing outputs. Full webpack project typechecking remains open.

The feature-table contract merges original override JSON and excludes explicit
`nocompile` entries, matching the original compiler's documented behavior.
Download code records an additional native dependency on the original enterprise
obfuscation library under the broader content-analysis flag. Original GN edges
remain recorded. DomDistiller's two Python protoc plugins use the existing native
launcher and declared interpreter with the pinned pure-Python protobuf backend.

Default-app package loading and action analysis pass with zero local build
actions. Hosted generator execution, full ELF linkage, runtime assembly and
native launch remain required. Other source triples remain unfinished.


The complete executable/test graph analyzes: 132,721 actions, 67,499 C++
compilations, 330 links and three Node project actions. Link actions are present
for the main executable, sandbox helper and Crashpad handler. The component's
actual files-to-build include `default_app.asar`. No CMake/foreign-cc mnemonics
appear; local analysis executes zero build actions. These results establish
action ownership, not successful generator execution or linkage.


WebUI contracts decode GRIT's default gzip discovery HTML before comparing the
original source bytes. Branding checks read the original unscaled resource pack,
following the captured repack graph. Final runtime resource checks retain the
component payload and plain WebID image comparisons.

### Linux distribution inputs

`tools/capture_runtime_inputs.py` maps the original Linux AMD64 distribution
manifest to GN producers. Capture requires `generate_about_credits = true`;
placeholder credits fail. The checked-in catalog contains 73 runtime paths,
including original license/version producers, locales, snapshots, packs and
default-app ASAR. It records the sandbox's required filename normalization and
omits a shared FFmpeg file when the captured target links FFmpeg statically.

The producer catalog is metadata only. The new
[`source/credits`](../bcr/overlay/source/credits/README.md) action closes the
original scanner's inputs and replaces the WebUI development sample with real
credits. Its 1,391 hashed inputs preserve 766 directories and 706 valid metadata
records, including 466 shipped entries. The
[BB consumer preflight](https://formatjs.buildbuddy.io/invocation/5f518c70-a6df-4842-8a20-b9013d660105)
passed hosted HTML generation, reproducibility and the complete shipped-license
test.

`source/distribution:metadata` stages the original Electron LICENSE and generated
Chromium notices, plus `version` from Electron's original template action and
generated version arguments. Its BB test checks release identity and unchanged
notice bytes. The same BB preflight passed original version generation and
notice staging; the original default-app ASAR test passed too.

Runtime assembly still requires portable shared-library layout and native
launch. The main executable, sandbox and Crashpad staging actions now declare
Python directly, use an empty PATH and normalize executable modes/timestamps.

SDK shared-library imports now carry the pinned runtime manifest's `DT_NEEDED`
edges, with explicit host ABI exclusions. The previous consumer failed loading
`libpixman-1.so.0` in a platform generator. A narrow Cairo paint test exercises
that loader path before the full source suite. Analysis confirms pixman enters
its link closure; native execution and full runtime launch remain unverified.


GN's JSON export merges private, public and data dependencies. Maintainer capture
now records each kind through temporary metadata instrumentation, restores
`BUILDCONFIG.gn`, then verifies every original target field and existing metadata
against an uninstrumented capture. All 28,340 targets matched. The platform
profile retains complete traversal edges, but only private/public edges provide
`CcInfo`; runtime-only edges use Bazel `data`. This removes accidental linkage
to ANGLE's Vulkan mock ICD. BB validation remains pending; complete Electron
remains unfinished.

The `88a79ce` dependency split passed the
[component preflight](https://formatjs.buildbuddy.io/invocation/bbf681f7-487f-4b3a-aad4-b97cb5d189fc)
(including typed-edge regression tests) and
[graphics probe](https://formatjs.buildbuddy.io/invocation/a66e2330-7893-48d2-af84-e1bf6605049d).
The consumer also passed native-generator, policy, tracing, API-feature and
version probes before its hosted free-tier timeout. Both large builds were still
compiling Blink when disconnected. No new compiler error was captured; complete
Electron remains unverified.

The next source probe targets two compile failures reached during `d0d8472`:
message-center's public header needs the captured ChromeOS feature header;
libaddressinput needs its generated `messages.h` include directory from the
owning WebUI GRIT repository. The metadata declares both at their provider.
`platform_header_compile_probes` builds the original libraries before broad
source tests. The `2d3f9b1`
[component compile probe](https://formatjs.buildbuddy.io/invocation/83ff59d7-b42c-4914-a1e8-999c0d469e32)
passed both original libraries on BB, followed by the
[graphics tests](https://formatjs.buildbuddy.io/invocation/b50aab0f-0d65-41dd-a221-fc7ac3eed001).
Broad source builds remain live; complete Electron remains unverified.
The next probe uses native `compilation_outputs` to avoid rebuilding dependency
archives before checking these scoped translation units.

The broad `2d3f9b1` build reached scoped Crashpad, GTK Unix printing,
message-center Ash and spellchecker locale-header failures. The next revision
adds their existing SDK/source/provider include contexts, plus compile-only
probes of each original library. No host headers enter those providers.

Printing also exposed libc++ tree desugaring of a specialized `std::less`.
The minimal BB [repro failed](https://formatjs.buildbuddy.io/invocation/0bc651cb-7bf1-40ba-b648-c32b3fd3e48f);
an explicit comparator wrapper [passed](https://formatjs.buildbuddy.io/invocation/63b9fda3-98f5-4138-9919-1b374c3e35b6).
The source patch preserves that specialized identity comparison and makes its
field ordering lexicographic. A real printing Mojo wire test checks crossed
identities in both insertion orders and rejects equal identities with different
paper geometry. Original-library compilation and wire execution remain pending
BB validation; complete Electron remains unverified.

The `269f3c2` consumer preflight advanced to GTK compatibility macro fragments:
`gtk_compat.h` includes five `.sigs` files already captured for stub generation,
but those files also need C++ compiler inputs. The next capture exposes them as
textual headers on the original GTK and Electron stub providers. Other profile
fields stay unchanged. Original-library and printing wire validation remain
pending; the previous preflight stopped before running the wire test.

The `532f86e` consumer passed the original-library
[compile-only probe](https://formatjs.buildbuddy.io/invocation/486abc78-7992-40ea-9043-7a7f958db6ef),
including Crashpad, GTK, message-center, spellchecker and printing. Its
[printing wire test](https://formatjs.buildbuddy.io/invocation/f525cbeb-de5b-4b70-ba7b-cc80fbbb926d)
then aborted because Mojo was not initialized. The test now links the existing
Mojo embedder and initializes it before serialization. Runtime validation remains
pending; complete Electron remains unverified.

The `416f428` components workflow passed the original-library
[compile probe](https://formatjs.buildbuddy.io/invocation/9608d7c3-de5a-4f31-852a-2fb64453c615),
[printing wire test](https://formatjs.buildbuddy.io/invocation/d4c98c88-88ec-4bfc-b71d-ee2794de4366)
and [graphics tests](https://formatjs.buildbuddy.io/invocation/0c982c98-9671-4fd3-a141-5918f3318e0d).
The wire test exercised successful round trips in both insertion orders and
the expected duplicate-paper rejection. Broad source builds remain unverified.

The broad `416f428` build reached missing Credential Manager interface and
shared message-enum headers. Both are now declared on their original consuming
libraries. Autofill metrics also hit the existing libc++ `unique_ptr::operator*`
projection issue; its equivalent dereference lambda follows the cookie-store
fix. Compile-only probes now cover all three owning libraries. The header change
is guarded to alter only two file entries and the corresponding owner header
lists. BB validation remains pending; the live broad build is still warming
unaffected actions.

The Chrome shim also needs `ash/ash_export.h` and the existing PDF GRIT
provider's generated-header include context. Both now belong to its declared
inputs/dependencies, with that original library added to compile probes. The
metadata guard limits this follow-up to one file entry and the shim's header and
dependency fields. Validation remains pending.

The finished broad run also reached Safe Browsing interface-header omissions and
Electron's `gio/gdesktopappinfo.h` include. Electron now depends on the existing
native GLib `gio_unix` provider. Safe Browsing header closure remains open; the
next compile probe will validate these fixes before another broad build.

The next capture declares source-header inventories for the missing Captive
Portal, fullscreen-control and Safe Browsing interfaces on the Chrome shim;
Electron's library receives the Safe Browsing interfaces too. Paths come from
the pinned Chromium tree. The semantic guard limits the profile update to 140
new file entries and those two owner header lists. Captured Safe Browsing flags
and library dependencies remain intact. BB validation is pending.

The 6f5a084 consumer stopped during preflight on a GitHub HTTP 504 fetching
`patchelf-0.19.1.tar.gz`; compilation did not run. The queued bootstrap prefetch
uses public release asset 468524906 and verifies BCR SHA-256
`491108728f120ce05b539934b41a750235031a6df8abc6b47e57aff7de15094d`
before Bazel consumes the unchanged source archive from `--distdir`. The official
Bazel mirror returned 404. No binary tool download or build wrapper is involved.

The 6f5a084 component probe passed preflight, then reached missing security-
interstitial headers through Safe Browsing and sign-in headers through
accessibility. Their pinned source inventories now belong to the Chrome shim;
Electron also receives security-interstitial headers. The metadata guard allows
only new file entries and these two owner header lists. Feature flags and link
dependencies remain unchanged. Hosted compilation is pending.

The ASAR reader now uses a shared bounded resolver for chained file/directory
links and root aliases. `Realpath` returns the canonical archive path;
`CopyFileOut` uses it for unpacked sidecars and extracted-file cache keys.
`Stat` still reports a final link as a link. A focused native test checks the
resolver against pinned Chromium dictionaries, including cycles and Windows
separators. The original Electron library owns the declared helper dependency.
BB compilation, reader integration and full-runtime filesystem smoke remain
unverified; bootstrap runtimes do not contain this patch.

A queued focused reader target compiles the real `archive.cc`, `asar_util.cc`
and `scoped_temporary_file.cc` with declared base/crypto/libuv/fuse dependencies.
Its test writes an ASAR fixture, exercises canonical sidecar reads and writes,
checks shared packed-file extraction identity, preserves link stats, enumerates
a directory alias and rejects cycles. This avoids linking Blink while testing
the production reader methods. BB compilation and execution remain pending.

The 0a54b87 component run passed the scoped
[compile probe](https://formatjs.buildbuddy.io/invocation/cc0d352a-8e26-4861-8f15-b72b923d8880),
[printing wire test](https://formatjs.buildbuddy.io/invocation/d3bab36c-4dbf-4c20-83f6-ffaaa6ad7c8a)
and [graphics test](https://formatjs.buildbuddy.io/invocation/69fb60ff-5374-4c98-b734-58da0696a056).
The broad build reached Electron linking, then failed because the original GN
flags still named `obj/third_party/electron_node/deps/uv/libuv.a`. The queued
translation replaces that exact input on `//electron:electron_app` with the
existing Electron-patched native libuv provider. Captured GN metadata stays
intact; no prebuilt archive or foreign build action is introduced. Linking and
full-runtime launch remain unverified.

The 6c5ad31 [consumer preflight](https://formatjs.buildbuddy.io/invocation/2ad91d1f-91e3-4950-a76a-65a631b812cd)
passed both ASAR tests. The reader target compiles the actual patched archive,
ASAR utility and temporary-file sources, then checks canonical sidecar reads and
writes, shared extraction identity, link stats, directory aliases and cycles.
Full Electron filesystem smoke remains unverified. Cross probes also passed;
both source workflows subsequently failed at the final Electron link.

The 6c5ad31 component build passed reader, compile, printing and graphics probes,
then reached duplicate definitions at the final Electron link. The pinned GN
Chrome shim is a static archive; some of its sources also belong to forced-in
source sets. Interleaving lazy archives before those source sets extracts members
which GN's object-first link would leave unused. The executable link
adapter keeps every forced source-set input first, then preserves the original
order of lazy inputs. Sources, compile flags, initializers and captured metadata
stay intact. Plain/ThinLTO regression fixtures check duplicate resolution and an
otherwise unreferenced constructor. The b351244
[BB preflight](https://formatjs.buildbuddy.io/invocation/061bb911-50ec-47c4-88b4-0b1041802607)
passed both fixtures and the real ASAR reader. The scoped header compile and
printing test also passed. Full Electron linking and runtime smoke remain
unverified at that preflight.

The b351244 [component build](https://formatjs.buildbuddy.io/invocation/78ca97f3-df63-4622-8463-e54531bc689e)
cleared the Electron link, then runtime assembly rejected missing `libnspr4.so`
and `libnss3.so`. The queued fix bundles the existing native NSS/NSPR producers,
including loadable NSS modules and notices. It regenerates `.chk` files from
the final RPATH-adjusted bytes with the existing deterministic integrity tool.
A relocated fixture checks original NSS module verification, initialization,
random generation and rejection of modified modules/checksums. BB validation
and full-runtime launch remain pending.

The queued runtime smoke also reads chained unpacked aliases through sync/async
`fs`, resolves canonical paths, checks directory aliases and `lstat`, and requires
the same CommonJS module through each alias. It compares packed alias extraction
inodes, writes through an unpacked alias descriptor and rejects cycles. These
checks run in the relocated source Electron browser process before renderer/IPC
validation; they have not passed BB yet.

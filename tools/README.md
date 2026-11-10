# Runtime package capture

`pin_platform_runtime.py` accepts `--architecture amd64` (default) or `arm64`.
It reads the corresponding SDK multiarch library paths and rejects mismatched
Debian package identities. ARM64 manifests must declare `"architecture":"arm64"`;
unmarked existing manifests mean AMD64. A capture never mixes architectures.

Run capture and validation on BB. The tool preserves SDK-matched package bytes,
records SHA-256 archive pins and reads dynamic metadata without executing target
libraries. This prepares ARM64 runtime inventories; it does not provide a complete
ARM64 Electron source profile. GN component profiles and native Bazel platform
selection still need separate capture and build validation.

# GN target capture

`capture_source.py`, `capture_base.py` and `capture_ipcz.py` accept
`--target-arch x64` (default) or `arm64`. They reject a different root toolchain
or component profile architecture. Unmarked component profiles mean x64.
Base and IPCz select the matching compiler builtins archive. Shared native
library capture uses each record's toolchain, including x64 Rust execution
libraries inside an ARM64 graph; Linux resource and uncompiled Objective-C
inventories stay separate. CXX execution tools retain their original x64
identities. Capture runs on BB, never target hardware.

```mermaid
flowchart LR
  graph[Pinned GN metadata] --> target[ARM64 target records]
  graph --> host[x64 execution records]
  target --> bazel[Native Bazel cross-build]
  host --> bazel
```

This is capture support, not an ARM64 source runtime. Actual ARM64 GN metadata,
Rust/Perfetto and remaining component profiles, SDK inventories and the complete
native Bazel cross-build still need validation. Keep qualified GN labels and host
records separate; replacing x64 strings across a graph can turn execution tools
into target binaries. GN only supplies maintainer metadata; no GN/Ninja build
action is introduced.

`prepare_source.py` can omit `--deps-cache`. This mode uses only the supplied
source/dependency roots and records `dependency_mode: declared-only`; missing
checkout files remain missing. Optional legacy caches still require matching
DEPS. Source bytes and checkout metadata remain unchanged.

Declared-only preparation derives `gclient_args.gni` from pinned Chromium DEPS
and Electron's parent overrides. It parses booleans and `Str(...)` literals,
rejects unsupported expressions and runs no checkout hooks. Generation replaces
private nodes; source symlinks and their targets stay immutable. Graph provenance
records the generated file's SHA-256.

Run edge capture against that private tree. Its temporary BUILDCONFIG.gn node
never writes through a source symlink; the original node is restored on failure.

The [isolated capture workspace](metadata_capture/README.md) pins GN, host/target
Rust libraries, SDKs and the native Bazel package tool. The BB-only runner keeps
target ARM64 records separate from x64 execution tools and records input hashes.

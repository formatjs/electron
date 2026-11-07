# Electron Bazel overlay

Build Electron from source using native Bazel actions. This repository owns the
`electron` BCR source overlay: exact source revisions, dependency patch stacks,
generators, native libraries and eventually the Electron runtime. App assembly,
ASAR, installers, signing and app runtime toolchains belong in a separate
`rules_electron` repository.

Full source-built Electron remains unfinished. Current components include
the full patched V8 engine and snapshots, patched libnode, Chromium base, ICU,
Perfetto, native networking, typed Mojo IPC, matching Skia with Rust PNG/fontations, native gfx/data packs, display models/wire types, UI events and X11 protocol code,
native UI colors/locales and the original WebUI resource pipeline,
native font/XML dependencies, libuv, BoringSSL, Node builtin generators, all eight Electron webpack bundles, fuses
and eleven Node support libraries (136 C/C++ units; Postject is header-only).
No target links a complete Electron executable.
See [source status and reproduction](docs/source-build.md).

## Layout

Matches [perplexityai/rocksdb](https://github.com/perplexityai/rocksdb):

- `bcr/`: module/source/metadata templates and presubmit configuration.
- `bcr/overlay/`: maintained Bazel files projected onto upstream Electron source.
- `tools/stage_bcr_entry.py`: version stamping and overlay integrity generation.
- `tests/bcr/`: independent consumer, with its own toolchain registration.
- `MODULE.bazel`: development module, `electron_development`.

The published source module is `electron`, versioned with Electron releases.
No module has been published. Existing app
packaging code was removed from this source-overlay workspace; Git history keeps
it available for the future rules repository.

## Develop

Use Bazel 9.2.0 or newer. Stage a fresh local registry after changing the overlay:

```sh
registry=$(mktemp -d)
python3 tools/stage_bcr_entry.py --source-registry bcr \
  --target-registry "$registry" --module electron --version 39.0.0
python3 tests/validate_bcr.py
bazel build --registry="file://$registry" --registry=https://bcr.bazel.build \
  //:source_components
bazel test --registry="file://$registry" --registry=https://bcr.bazel.build \
  //:source_tests //tests:prepare_source_test
```

The development workspace consumes the staged `electron` module, so builds use
exactly the source/overlay layout that downstream consumers receive. Use a fresh
registry when iterating; staging refuses to overwrite existing version entries.

Check the independent consumer:

```sh
cd tests/bcr
bazel test --registry="file://$registry" --registry=https://bcr.bazel.build \
  //:loop_consumer_test @electron//:source_tests
```

The archive's overlay includes the same consumer for BCR presubmit. Consumer
modules register Node 22.20.0, Python 3.11 and LLVM toolchains themselves; the
published module does not register toolchains for them.

## CI

[BuildBuddy configuration](buildbuddy.yaml) and [remote execution settings](.bazelrc)
follow [formatjs/chromium](https://github.com/formatjs/chromium). Hosted BuildBuddy
runs source-component builds, Linux integration tests, five-platform native
cross-link probes and the isolated BCR consumer. GitHub Actions runs metadata and
registry checks. Windows probes use MSVC; cross-linking does not establish native
execution. See [CI setup](tools/ci/README.md).

## Source compatibility

Select Electron release first, then its complete DEPS and ordered patch stacks.
This overlay pins Electron 39.0.0, Node 22.20.0, Chromium 142.0.7444.52 and the
matching V8 revision. Reuse hermeticbuild/nodejs and formatjs/chromium build
machinery while preserving Electron's patched dependency closure. Host Node build
tools stay separate from Electron's embedded target Node.

Repository code is MIT. Adapted registry staging code is Apache-2.0; see
[NOTICE](NOTICE). Upstream sources retain their own licenses.

# Maintainer capture inputs

Isolated Bazel workspace for BB Linux metadata capture. Its package-tool
dependencies do not change the production Electron module graph.

`//:inputs` fetches SHA-256-pinned GN, Chromium tooling, Bullseye x64/ARM64
sysroots, Rust nightly compiler and both standard libraries. Pins match Electron
39's Chromium 142 source capture. `//:pkg_config` builds pkgconf 3.0.10 through
native Bazel C rules. Default package/personality search directories are empty;
capture must supply the declared SDK metadata paths.

Build these targets on BB only, using `--config=buildbuddy`. Execution uses the
pinned Linux x64 OCI image with network disabled. GN runs only for maintainer
metadata; no Ninja build runs. The capture workflow still needs wiring and BB
validation. These inputs alone do not establish an ARM64 source profile.

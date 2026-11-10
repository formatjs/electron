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

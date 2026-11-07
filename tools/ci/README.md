# Electron CI

Follows formatjs/chromium: BuildBuddy owns Bazel builds and Linux source tests;
GitHub Actions runs Python metadata and registry checks. `--config=buildbuddy`
uses the FormatJS BES, remote cache and executor. The linked BuildBuddy GitHub
App supplies credentials through its Bazel wrapper; none are checked in.

Remote build actions use a digest-pinned Ubuntu 22.04 OCI image with external
networking disabled. `dockerNetwork=off` is intentional: BuildBuddy's generic
network property currently normalizes to `none`, while its OCI isolation check
expects `off`. A fresh remote TLS-denial test runs in both the development and
BCR consumer workspaces before source compilation;
`external`/`no-cache` tags prevent cached success from hiding executor changes.
Repository fetching remains outside build actions. C++/Apple/Swift host toolchain
discovery is disabled; target compilers and sysroots stay declared inputs.

`buildbuddy.yaml` stages a fresh registry per action. Development builds and the
isolated `tests/bcr` consumer both resolve the exact maintained overlay through
that registry. The consumer registers its own Node, Python and LLVM toolchains;
the published module does not register toolchains for downstream users.

Linux source tests execute on the hosted Linux worker. Five-platform libuv and
crypto probes cross-link remotely, using MSVC for Windows. Cross-link success
does not establish native runtime execution. Full Electron runtime artifacts do
not exist yet; native artifact smoke handoff can follow Chromium once they do.

BuildBuddy GitHub App installation and repository enablement remain external
setup. No hosted execution is claimed by checking in this configuration.

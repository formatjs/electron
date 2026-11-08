Linux x64 runtime assembly maps all 73 upstream distribution paths to declared
native Bazel outputs. The map comes from `tools/capture_runtime_inputs.py`;
missing or changed producers fail capture.

The ZIP places Electron, Crashpad, sandbox and graphics libraries at the root;
support libraries live in `lib/`. Native GLib/zlib outputs explicitly replace
their SDK copies. Other support libraries come from pinned Debian archives.
Notices retain original package text, SHA256 guards and complete common-license
texts. `tools/capture_runtime_copyrights.py` captures that data from the matching
runtime/SDK repositories, without executing library code.

The assembler runs declared Python and source-built `patchelf` with an empty
PATH. BCR's patchelf 0.19.1 overlay uses native `cc_binary`, without CMake or
foreign-cc. It patches copies, validates x86_64 ELF/interpreters/SONAMEs, requires
every DT_NEEDED dependency to be bundled or listed in the explicit host ABI,
and sets relative `$ORIGIN` search paths. Both isolated staging roots and changed
mtimes must produce identical ZIP bytes. Input hashes must remain unchanged.

The host ABI covers glibc, libgcc and libstdc++; this does not bundle the OS,
graphics drivers or desktop services. Dynamic plugin/data discovery still needs
native browser validation.

`archive_test` compiles real transitive DSOs, loads them after ZIP relocation
with no LD_LIBRARY_PATH and rejects missing dependencies or wrong SONAMEs.
`runtime_test` checks all upstream distribution paths, then runs relocated
Electron's embedded Node and `--version`. Its Ozone headless BrowserWindow checks
an app.asar packed by Electron's original generator, executable renaming,
packaged-app identity, isolated preload IPC, disabled renderer Node integration and actual rendered
HTML pixels, using a declared font/configuration and no display server or network
content. These checks remain unverified on BB; native runtime/app launch
remains open.

The BB preflight already passed original version generation, exact notice
staging, real Chromium credits and default-app ASAR generation. Archive fixture
and complete runtime action analysis passed. No assembly or fixture tests have
run locally.

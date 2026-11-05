# Bazel Electron

Build app payloads and package Electron apps using declared Bazel inputs. No
Electron Builder, package-manager install scripts, host Node, or network access
inside build actions. MIT rules; bundled upstream licenses stay intact.

```sh
bazel test //tests:package_test //source:loop_interrupt_test
bazel build //examples/hello:dist
```

`dist` produces Linux AMD64/ARM64, Darwin ARM64, Windows AMD64/ARM64 ZIPs from
SHA256-pinned official Electron 39.0.0 distributions. Packaging runs on Linux for
all five targets. `with_cfg` applies target platforms; packaging Python runs in
the execution configuration. Windows runtimes use MSVC.

```starlark
load("@rules_electron//electron:defs.bzl", "electron_app", "electron_packages")

electron_app(
    name = "app",
    app_name = "my-app",
    version = "1.0.0",
    main = "main.js",
    srcs = {":main_bundle": "main.js", ":renderer_bundle": "renderer.js"},
)
electron_packages(
    name = "dist",
    app = ":app",
    product_name = "MyApp",
    bundle_id = "org.example.myapp",
)
```

Map built JS, HTML, CSS, assets and native addons explicitly. Generated directory
outputs can map to `dist` or `node_modules`; dependency trees must materialize
files rather than use directory symlinks. `electron_package`
packages one selected platform; `electron_packages` produces all five. Supply
`runtime = ":custom_runtime"` to package a distribution produced from source;
`electron_runtime` accepts a ZIP, explicit version and target platform.

Consumer setup: add this module using a pinned `git_override`, configure
`@rules_electron//electron:extensions.bzl` with `version = "39.0.0"`, then
`use_repo(electron, "electron_runtime")`. See root `MODULE.bazel`.

ZIPs normalize timestamps, permissions and entry order; stream runtime files;
preserve framework symlinks and notices; reject duplicate paths, traversal and
escaping links. Windows renames executable and WER DLL. Darwin updates bundle
metadata. App payload currently uses Electron's supported `resources/app`
layout. ASAR, installers, native-addon ABI builds, icons, signing, notarization
and updates still need rules. Darwin packages require signing after rebranding;
smoke tests ad hoc sign locally. Release signing needs platform credentials.

Rendering smoke, Linux AMD64:

```sh
archive=$(bazel cquery //examples/hello:dist_linux_amd64 --output=files)
xvfb-run -a bazel run //tools:smoke -- \
  --package="$PWD/$archive" --screenshot=/tmp/electron.png
```

The example checks rendered DOM content, captures a real Electron window and
rejects empty rendering. Native smoke for the other four platforms needs their
respective runners. Cross-packaging success does not establish native launch.

## Building Electron itself

Full source-built Electron is **unfinished**. Runtime packaging uses official
prebuilt distributions. Source work already pins Electron 39.0.0, downloads its
full Node 22.20.0 git archive and applies every patch in Electron's Node stack
using Bazel's patch engine. `//source:node_libuv` compiles that patched source
with hermeticbuild LLVM 0.8.26. `loop_interrupt_test` executes Electron's
`UV_LOOP_INTERRUPT_ON_IO_CHANGE` API, absent from stock libuv.
`//source:cross_probes` compiles and links this API for all five target ABIs
with explicit MSVC Windows toolchains.

`electron_js2c` builds the actual patched Node C++ generator using hermetic
LLVM, patched libuv and BCR simdutf. It stages declared JS under stable builtin
names and runs the generator in the execution configuration.
`bazel build //source:embedder_javascript` produces Electron embedder builtin
registration C++; full libnode linkage still needs the matching patched V8.

Chromium work at `../bcr_overlays` supplies native Bazel actions and overlays.
Electron 39.0.0 pins Chromium **142.0.7444.52**; that repo currently pins
**142.0.7444.59**. Reuse requires an exact Electron-compatible Chromium source
revision and its patch stacks, not linking an unpatched Chromium/V8 build.
Electron also patches BoringSSL, DevTools, FFmpeg, V8, NAN, Perfetto,
Squirrel.Mac, Mantle, ReactiveObjC, WebRTC, reclient configuration and SQLite.

Next source steps: apply all matching patch stacks; capture patched
`//electron:electron` GN graphs per target; import Node/Electron libraries,
snapshot and JS generators into the existing native Bazel action model;
provide the resulting runtime ZIP to the same packaging rules. Keep host
generator runtimes private, stage their declared libraries and ICU beside the
resolved executable, and retain original executable runfiles basenames.

hermeticbuild/nodejs shares the LLVM toolchain, libnode source inventory,
V8 integration and dependency overlays. Its standalone Node build cannot
replace Electron's embedded Node: Electron patches Node's loop, loaders,
original-fs support, native builtins and V8 integration. Rust source targets
should use `rules_rs` as Chromium does; this initial source slice has no Rust.

Sources: [Electron packaging](https://www.electronjs.org/docs/latest/tutorial/application-distribution),
[Electron DEPS](https://github.com/electron/electron/blob/v39.0.0/DEPS),
[Electron patch stacks](https://github.com/electron/electron/blob/v39.0.0/patches/config.json),
[hermeticbuild Node](https://github.com/hermeticbuild/nodejs).

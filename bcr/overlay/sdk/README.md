# Source addon SDK

`@electron//sdk:node_v8_addon_sdk` exposes `CcInfo` for addons loaded by this
source-built runtime. It supplies the patched Node/libuv headers, matching V8
headers and producer ABI settings, including Electron's module version. It
exports compilation context only; addons must not link Node or V8 archives.

With `rules_electron`:

```starlark
electron_cc_addon(
    name = "addon",
    srcs = ["addon.cc"],
    headers = "@electron//sdk:node_v8_addon_sdk",
)
```

Use the producer's configured LLVM toolchain and C++ runtime. The bootstrap
release SDK's Chromium libc++ configuration does not describe this native Bazel
producer. Current SDK support follows the source runtime: Linux x86_64.

`probe.node` exercises V8 backing-store shared ownership across the C++ boundary.
The standalone runtime test loads it after relocation and executable renaming,
checks bytes in the main thread and a worker, and runs in both ASCII/C and
Unicode/C.UTF-8 directories. Native BB validation remains pending.

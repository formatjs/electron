# RFC: source profile families

Status: Linux ARM64 GN metadata captured. Native profile port in progress.

One family represents a runtime OS/CPU. It owns target libraries and every
execution variant needed to build them. Family selection lives in target labels,
so execution transitions keep the runtime's snapshot settings.

```mermaid
flowchart LR
  graph[Pinned Linux ARM64 GN graph] --> target[ARM64 target profiles]
  graph --> execution[x64 generator profiles]
  graph --> snapshot[x64 ARM64 V8 snapshot profiles]
  graph --> rust[x64 Rust host profiles]
  target --> build[Native Bazel cross-build]
  execution --> build
  snapshot --> build
  rust --> build
  build --> runtime[ARM64 Electron archive]
```

The captured graph has 11,474 ARM64 records, 680 ordinary x64 records, 6,998 x64
V8 snapshot records and 70 Rust host records. Base and Perfetto exist in several
toolchains. Bare-label lookup would merge different sources, flags and owners.

`LinuxGraph.resolve(label, role)` is the identity interface. It selects the exact
GN toolchain and rejects missing, ambiguous or inconsistent records. Keep
qualified labels through capture and hash them into distinct target names.
Compiler architecture comes from each record; snapshot tools compile for x64
while retaining ARM64 V8 settings.

Store profiles by family, module and role. Bind generated repositories to that
same identity; macros accept profile data and owned dependency labels. For
example, a snapshot Base library belongs to the ARM64 family and compiles under
execution configuration. Preserve existing x64 defaults during the port.

Resolve external providers through the family's owner map. Shared source
archives can be reused. Libraries can be shared only after comparing their
captured configuration. Runtime selection follows the requested target platform;
generator execution never selects an ARM64 target executable.

Port modules in dependency order, then cross-build the complete archive and
desktop SDK. Keep native smoke on available matching hosts. Linux ARM64 currently
has no smoke host. The captured graph alone does not establish a source runtime.

Perfetto capture accepts target, execution and snapshot roles. Each profile keeps
qualified dependencies, compiler architecture and generated include roots. ARM64
profiles leave external owners unbound; `electron_perfetto(profile, external)`
rejects missing owners. No ARM64 dependency silently uses the x64 default. The
capture workflow exports all three profiles. Cross-building those profiles and
the remaining family modules is still required.

V8 support capture follows each role's dependency closure, including ARM64's
`zlib_arm_crc32` instead of x64's `zlib_crc32_simd`. Ordinary execution capture
needs only zlib; target and snapshot capture retain V8's number and SIMD
libraries. Compiler builtins and generated include roots must match each role.
The native macro accepts a profile explicitly; complete family registration and
ARM64 compiler validation remain open.


The maintainer workflow projects each captured support profile into a temporary
repository using declared source roots. A graph digest, family/role identity and
source path checks precede projection. Bazel then audits and compiles every
library for Linux ARM64 or x64 with the pinned GNU 2.31 toolchain. Compilation
runs on BB; this step executes no target binaries. This validates support
profiles before registering the complete runtime family.


Protobuf capture selects `protobuf_lite` for ARM64 target and snapshot profiles,
and `protoc` plus compiler plugins for ordinary execution. Qualified Abseil
aggregate dependencies remain in each profile. Staging binds them explicitly to
the pinned upstream native Bazel targets under that role's compiler platform;
missing or cross-role identities fail. Protobuf safety defines and builtins stay
checked. BB compiles all three profiles after their action audits.

Perfetto validation binds each role's zlib profile and the ordinary x64 Protobuf
compiler profile together. Host libraries stay out of the target archive group;
generator dependencies build in execution configuration. Action queries receive
all repository overrides used by the native build. The workflow compiles the
complete Perfetto closure for target, execution and snapshot roles.

Generator interpreters resolve through an execution-configured dependency.
Resolving Python directly in a target rule selected ARM64 Python for an x64 BB
worker and failed with `Exec format error`. Source actions, artifact staging,
runtime assembly, Node project wrappers and native tool staging share the
execution runtime provider. Cross-platform probes execute the generator under
Linux x64/ARM64, macOS ARM64 and Windows x64/ARM64 target configurations.

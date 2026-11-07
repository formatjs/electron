"""Complete captured Temporal crates, build scripts and original allocator FFI."""

load("@electron_rust_sources//:profile.bzl", "PROFILE")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_rs//rs:cargo_build_script.bzl", "cargo_build_script")
load("@rules_rs//rs:rules_rust_bindgen.bzl", "rust_bindgen")
load("@rules_rs//rs:rust_binary.bzl", "rust_binary")
load("@rules_rs//rs:rust_library.bzl", "rust_library")
load("@rules_rs//rs:rust_proc_macro.bzl", "rust_proc_macro")
load("@rules_rust//rust:rust_common.bzl", "BuildInfo")

_LINUX_AMD64 = ["@platforms//os:linux", "@platforms//cpu:x86_64"]

def _file(path):
    for package in PROFILE["packages"]:
        if path.startswith(package + "/"):
            return "//" + package + ":" + path[len(package) + 1:]
    return "//:" + path

def _allocator_flags_impl(ctx):
    flags = PROFILE["allocator_buildflags"]
    output = ctx.actions.declare_file(ctx.label.name + "/" + flags["output"])
    response = ctx.actions.declare_file(ctx.label.name + ".rsp")
    ctx.actions.write(response, " ".join(flags["response"]))
    ctx.actions.run(
        executable = ctx.attr._runner[DefaultInfo].files_to_run,
        arguments = [ctx.file._script.path, "--output", flags["output"], "--rulename", flags["rule"], "--gen-dir", output.path[:-len(flags["output"]) - 1], "--definitions", response.path],
        inputs = [ctx.file._script, response],
        outputs = [output],
        env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronRustAllocatorBuildflags",
    )
    return [DefaultInfo(files = depset([output]))]

_allocator_flags = rule(
    implementation = _allocator_flags_impl,
    attrs = {
        "_script": attr.label(default = Label("@electron_chromium_sources//:build/write_buildflag_header.py"), allow_single_file = True),
        "_runner": attr.label(default = Label("//electron/private:run_source"), executable = True, cfg = "exec"),
    },
)

def _bindings_impl(ctx):
    output = ctx.actions.declare_directory(ctx.label.name)
    ctx.actions.run(
        executable = ctx.attr._runner[DefaultInfo].files_to_run,
        arguments = [ctx.file.src.path, output.path],
        inputs = [ctx.file.src],
        outputs = [output],
        env = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
        mnemonic = "ElectronRustBindingsLayout",
    )
    return [
        DefaultInfo(files = depset([output])),
        ctx.attr.cc_lib[CcInfo],
        BuildInfo(out_dir = output, compile_data = depset([output]), dep_env = None, rustc_env = None, flags = None, linker_flags = None, link_search_paths = None),
    ]

_bindings = rule(
    implementation = _bindings_impl,
    attrs = {
        "src": attr.label(allow_single_file = True),
        "cc_lib": attr.label(providers = [CcInfo], mandatory = True),
        "_runner": attr.label(default = Label("//electron/private:copy_bindings"), executable = True, cfg = "exec"),
    },
)

def electron_temporal():
    """Declare the exact runtime/host crate variants behind the stable source shim."""
    repository_root = Label("@electron_rust_sources//:BUILD.bazel").workspace_root
    native.exports_files(PROFILE["root_files"] + ["BUILD.bazel", "profile.bzl"])
    _allocator_flags(name = "allocator_buildflags")
    allocator_headers = {"build/build_config.h": True, "build/buildflag.h": True}
    for library in PROFILE["cpp"].values():
        allocator_headers.update({path: True for path in library["hdrs"]})
    cc_library(
        name = "allocator_headers",
        hdrs = sorted(allocator_headers),
        includes = ["."],
        target_compatible_with = _LINUX_AMD64,
    )
    cc_library(
        name = "allocator_buildflag_headers",
        hdrs = [":allocator_buildflags"],
        strip_include_prefix = "allocator_buildflags",
        target_compatible_with = _LINUX_AMD64,
    )
    for library in PROFILE["cpp"].values():
        cc_library(
            name = library["name"],
            srcs = library["srcs"],
            copts = library["copts"],
            local_defines = library["defines"],
            linkstatic = True,
            target_compatible_with = _LINUX_AMD64,
            deps = [":allocator_headers", ":allocator_buildflag_headers"] + (["@electron_partition_alloc_sources//:partition_alloc"] if library["partition_alloc"] else []),
        )
    for label, ffi in PROFILE["ffi"].items():
        crate = PROFILE["rust"][label]
        rust_bindgen(
            name = crate["name"] + "_generator",
            header = ffi.get("header_label", _file(ffi["header"])),
            cc_lib = ffi["owner"] if ffi["owner"].startswith("@") else ":" + ffi["owner"],
            bindgen_flags = ffi["bindgen_flags"],
            clang_flags = ["-x", "c++", "-std=c++20", "-fparse-all-comments", "-fvisibility=default"],
            target_compatible_with = _LINUX_AMD64,
        )
        _bindings(name = crate["name"] + "_bindings", src = ":" + crate["name"] + "_generator", cc_lib = ffi["owner"] if ffi["owner"].startswith("@") else ":" + ffi["owner"])
    for label, crate in PROFILE["rust"].items():
        environment = dict(crate["rustc_env"])
        if "CARGO_MANIFEST_DIR" in crate["rewritten_paths"]:
            environment["CARGO_MANIFEST_DIR"] = repository_root + "/" + (crate["package"] or crate["crate_root"].rpartition("/")[0])
        settings = dict(
            name = crate["name"],
            crate_name = crate["crate_name"],
            crate_root = _file(crate["crate_root"]),
            srcs = [_file(path) for path in crate["srcs"]],
            edition = crate["edition"],
            crate_features = crate["features"],
            rustc_flags = crate["rustc_flags"],
            rustc_env = environment,
            deps = [":" + name for name in crate["deps"]] + crate.get("cc_deps", []),
            proc_macro_deps = [":" + name for name in crate["proc_macro_deps"]],
            compile_data = ["//" + crate["package"] + ":files"] if crate["package"] else [],
            target_compatible_with = _LINUX_AMD64,
        )
        if label in PROFILE["ffi"]:
            settings["deps"] += [":" + crate["name"] + "_bindings"]
        if crate["kind"] == "cargo_build_script":
            settings["version"] = environment.get("CARGO_PKG_VERSION", "")
            settings["pkg_name"] = environment.get("CARGO_PKG_NAME", "")
            settings["data"] = ["//" + crate["package"] + ":files"]
            settings["build_script_env"] = {"CARGO_MANIFEST_DIR": repository_root + "/" + crate["package"]}
            settings["use_default_shell_env"] = False
            cargo_build_script(**settings)
        elif crate["kind"] == "rust_proc_macro":
            rust_proc_macro(**settings)
        elif crate["kind"] == "rust_library":
            rust_library(**settings)
        elif crate["kind"] == "executable":
            rust_binary(**settings)
        else:
            fail("Unsupported Temporal Rust target kind")
    cc_library(
        name = "temporal_headers",
        hdrs = [_file(path) for path in PROFILE["cpp_headers"]],
        includes = ["third_party/rust/chromium_crates_io/vendor/temporal_capi-v0_1/bindings/cpp"],
        defines = ["TEMPORAL_CAPI_VERSION_0_1"],
        target_compatible_with = _LINUX_AMD64,
    )
    cc_library(name = "temporal_capi", deps = [":" + PROFILE["root"], ":temporal_headers"], target_compatible_with = _LINUX_AMD64)
    rust_library(
        name = "allocator_probe",
        testonly = True,
        srcs = [Label("//source:rust_allocator_probe.rs")],
        crate_root = Label("//source:rust_allocator_probe.rs"),
        crate_name = "electron_allocator_probe",
        edition = "2021",
        rustc_flags = ["-Dunsafe_op_in_unsafe_fn"],
        target_compatible_with = _LINUX_AMD64,
        deps = [":" + PROFILE["rust"]["//build/rust/allocator:allocator"]["name"]],
    )
    native.filegroup(name = "crates", srcs = [":" + PROFILE["root"]] + [":" + library["name"] for library in PROFILE["cpp"].values()])
    for alias_name, original in {
        "base_logger": "//base:rust_logger",
        "serde_json_wrapper": "//third_party/rust/serde_json_lenient/v0_2/wrapper:wrapper",
        "cxxbridge": "//third_party/rust/cxxbridge_cmd/v1:cxxbridge(//build/toolchain/linux:clang_x64_for_rust_host_build_tools)",
        "cxx_runtime": "//third_party/rust/cxx/v1:lib",
    }.items():
        native.alias(name = alias_name, actual = ":" + PROFILE["rust"][original]["name"])

"""Compile/link Electron's patched Node loop on each requested target ABI."""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@with_cfg.bzl", "with_cfg")
load("//electron:source_action.bzl", "electron_source_action")

linux_amd64_probe, _linux_amd64 = with_cfg(cc_binary).set("platforms", [Label("@llvm//platforms:linux_x86_64_gnu.2.31")]).build()
linux_arm64_probe, _linux_arm64 = with_cfg(cc_binary).set("platforms", [Label("@llvm//platforms:linux_aarch64_gnu.2.31")]).build()
darwin_arm64_probe, _darwin_arm64 = with_cfg(cc_binary).set("platforms", [Label("@llvm//platforms:macos_aarch64")]).build()
windows_amd64_probe, _windows_amd64 = with_cfg(cc_binary).set("platforms", [Label("@llvm//platforms:windows_x86_64_msvc")]).build()
windows_arm64_probe, _windows_arm64 = with_cfg(cc_binary).set("platforms", [Label("@llvm//platforms:windows_aarch64_msvc")]).build()

linux_amd64_python_probe, _linux_amd64_python = with_cfg(electron_source_action).set("platforms", [Label("@llvm//platforms:linux_x86_64_gnu.2.31")]).build()
linux_arm64_python_probe, _linux_arm64_python = with_cfg(electron_source_action).set("platforms", [Label("@llvm//platforms:linux_aarch64_gnu.2.31")]).build()
darwin_arm64_python_probe, _darwin_arm64_python = with_cfg(electron_source_action).set("platforms", [Label("@llvm//platforms:macos_aarch64")]).build()
windows_amd64_python_probe, _windows_amd64_python = with_cfg(electron_source_action).set("platforms", [Label("@llvm//platforms:windows_x86_64_msvc")]).build()
windows_arm64_python_probe, _windows_arm64_python = with_cfg(electron_source_action).set("platforms", [Label("@llvm//platforms:windows_aarch64_msvc")]).build()

def loop_probes():
    targets = []
    for platform, implementation in [("linux_amd64", linux_amd64_probe), ("linux_arm64", linux_arm64_probe), ("darwin_arm64", darwin_arm64_probe), ("windows_amd64", windows_amd64_probe), ("windows_arm64", windows_arm64_probe)]:
        name = "loop_" + platform
        implementation(name = name, srcs = ["loop_interrupt_test.c"], deps = [":node_libuv"])
        targets.append(":" + name)
        crypto = "crypto_" + platform
        implementation(name = crypto, srcs = ["crypto_compat_test.cc"], deps = ["@electron_boringssl_sources//:ssl"])
        targets.append(":" + crypto)
    for platform, implementation in [("linux_amd64", linux_amd64_python_probe), ("linux_arm64", linux_arm64_python_probe), ("darwin_arm64", darwin_arm64_python_probe), ("windows_amd64", windows_amd64_python_probe), ("windows_arm64", windows_arm64_python_probe)]:
        name = "execution_python_" + platform
        implementation(
            name = name,
            srcs = {"python_execution_probe.py": "python_execution_probe.py"},
            script = "python_execution_probe.py",
            args = ["probe.txt"],
            logical_outputs = ["probe.txt"],
            out_files = [name + ".txt"],
        )
        targets.append(":" + name)
    native.filegroup(name = "cross_probes", srcs = targets)

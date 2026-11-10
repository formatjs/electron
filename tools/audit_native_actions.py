"""Check native compiler presence and reject build-wrapper action mnemonics."""

import argparse
import re
import subprocess
import sys


FORBIDDEN = r"(?i)^(.*(foreign.?cc|cmake|meson|ninja).*|g?make|runmake|gn|rungn)$"
TARGETS = ("@electron//:source_components", "@electron//source:cross_probes", "//:pkg_config", "@electron_v8_support_sources//:libraries")


class AuditFailure(ValueError):
    pass


def action_count(summary):
    lines = summary.strip().splitlines()
    if lines == ["No actions matched."]:
        return 0
    if not lines or not re.fullmatch(r"[1-9][0-9]* total actions?\.", lines[0]):
        raise AuditFailure("summary")
    total = int(lines[0].split()[0])
    if "Mnemonics:" not in lines:
        raise AuditFailure("summary")
    counts = []
    for line in lines[lines.index("Mnemonics:") + 1:]:
        if not line:
            break
        match = re.fullmatch(r"  [A-Za-z_][A-Za-z_0-9]*: ([1-9][0-9]*)", line)
        if not match:
            raise AuditFailure("summary")
        counts.append(int(match[1]))
    if sum(counts) != total:
        raise AuditFailure("summary")
    return total


def audit_summaries(compilers, wrappers):
    count = action_count(compilers)
    if count == 0 or not re.search(r"(?m)^  CppCompile: " + str(count) + r"$", compilers):
        raise AuditFailure("compiler")
    if action_count(wrappers) != 0:
        raise AuditFailure("wrappers")
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--downloader-config", required=True)
    parser.add_argument("--distdir", required=True)
    parser.add_argument("--target", choices=TARGETS, default=TARGETS[0])
    parser.add_argument("--support-override")
    parser.add_argument("--support-platform", choices=("linux_amd64", "linux_arm64"))
    args = parser.parse_args()
    support = args.target == "@electron_v8_support_sources//:libraries"
    if (support and not (args.support_override and args.support_platform)
            or not support and (args.support_override or args.support_platform)):
        parser.error("Support audit requires repository and platform together")
    cross = args.target == "@electron//source:cross_probes"
    metadata = args.target == "//:pkg_config"
    command = ["bazel"] + ([] if metadata else ["--host_jvm_args=-Xmx" + ("12g" if cross or support else "24g")])
    command += ["aquery", "--config=buildbuddy",
               "--downloader_config=" + args.downloader_config, "--distdir=" + args.distdir,
               "--include_aspects", "--output=summary"]
    if not metadata:
        command += ["--registry=" + args.registry, "--registry=https://bcr.bazel.build"]
    if support:
        command += ["--override_repository=" + args.support_override,
                    "--platforms=@electron//source/platforms:" + args.support_platform]
    if cross:
        command += ["--repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1",
                    "--repo_env=BAZEL_WINDOWS_SDK_EULA=1"]
    try:
        summaries = []
        roots = args.target if cross or metadata or support else "set(" + args.target + " @electron//:source_tests)"
        for expression in ("CppCompile", FORBIDDEN):
            query = 'mnemonic("' + expression + '", deps(' + roots + '))'
            result = subprocess.run(command + [query], check=True, capture_output=True, text=True)
            if len(result.stdout) > 1024**2:
                raise AuditFailure("summary")
            summaries.append(result.stdout)
        count = audit_summaries(*summaries)
    except Exception as error:
        # Bazel diagnostics can include private execution-platform settings.
        reason = str(error) if isinstance(error, AuditFailure) and str(error) in ("summary", "compiler", "wrappers") else "query" if isinstance(error, subprocess.CalledProcessError) else "internal"
        print("NATIVE_ACTION_AUDIT_FAILED reason=" + reason, file=sys.stderr)
        return 1
    print("NATIVE_ACTION_AUDIT_PASSED compile_actions=" + str(count) + " forbidden_actions=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())

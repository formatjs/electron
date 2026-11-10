"""Explicit Linux GN target identity; execution tools remain separate."""

TRIPLES = {'x64': 'x86_64-unknown-linux-gnu', 'arm64': 'aarch64-unknown-linux-gnu'}
_RUST_EXECUTION = '//build/toolchain/linux:clang_x64_for_rust_host_build_tools'
_ARM64_SNAPSHOT = '//build/toolchain/linux:clang_x64_v8_arm64'


def target_toolchain(architecture):
    if architecture not in TRIPLES:
        raise ValueError('Unsupported captured Linux target architecture')
    return '//build/toolchain/linux:clang_' + architecture


def toolchain_architecture(toolchain):
    return {target_toolchain('x64'): 'x64', target_toolchain('arm64'): 'arm64',
            _RUST_EXECUTION: 'x64', _ARM64_SNAPSHOT: 'x64'}.get(toolchain)


class LinuxGraph:
    """Resolve GN identity by role; preserve qualified execution records."""

    def __init__(self, graph, target_arch):
        validate_profile_target(graph, target_arch)
        self._targets = graph['targets']
        self._roles = {'target': target_toolchain(target_arch), 'execution': target_toolchain('x64'),
                       'snapshot': _ARM64_SNAPSHOT if target_arch == 'arm64' else target_toolchain('x64'),
                       'rust_execution': _RUST_EXECUTION}
        self._index = {}
        for label, record in self._targets.items():
            bare, separator, suffix = label.partition('(')
            toolchain = record.get('toolchain')
            if not separator and toolchain != self._roles['target']:
                raise ValueError('Unqualified GN label differs from target toolchain')
            if separator and (not suffix.endswith(')') or suffix[:-1] != toolchain):
                raise ValueError('Qualified GN label differs from its toolchain')
            self._index.setdefault((bare, toolchain), []).append(label)

    def resolve(self, label, role='target'):
        if role not in self._roles:
            raise ValueError('Unknown GN capture role')
        toolchain = self._roles[role]
        bare, separator, _ = label.partition('(')
        matches = self._index.get((bare, toolchain), [])
        if len(matches) != 1 or separator and label != matches[0]:
            raise ValueError('Expected one GN label for capture role')
        return matches[0]

    def architecture(self, label):
        if label not in self._targets:
            raise ValueError('Unknown captured GN label')
        architecture = toolchain_architecture(self._targets[label].get('toolchain'))
        if architecture is None:
            raise ValueError('Unsupported captured Linux compiler toolchain')
        return architecture


def builtins_archive(architecture):
    target_toolchain(architecture)
    return '$LLVM_ROOT/lib/clang/23/lib/' + TRIPLES[architecture] + '/libclang_rt.builtins.a'


def validate_profile_target(profile, architecture):
    target_toolchain(architecture)
    if profile.get('target_arch', 'x64') != architecture:
        raise ValueError('Component profiles must share target architecture')


def validate_graph_target(graph, root, architecture):
    if graph['targets'][root].get('toolchain') != target_toolchain(architecture):
        raise ValueError('GN root does not match selected Linux target architecture')

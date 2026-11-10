"""Explicit Linux GN target identity; execution tools remain separate."""

TRIPLES = {'x64': 'x86_64-unknown-linux-gnu', 'arm64': 'aarch64-unknown-linux-gnu'}


def target_toolchain(architecture):
    if architecture not in TRIPLES:
        raise ValueError('Unsupported captured Linux target architecture')
    return '//build/toolchain/linux:clang_' + architecture


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

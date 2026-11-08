# SPDX-License-Identifier: MIT
"""Exercise the original Rust/C++/Rust panic path in an isolated child."""

from pathlib import Path
import resource
import signal
import subprocess
import sys


def require(condition, check):
    if not condition:
        raise ValueError("check failed: blink_crash " + check)


def disable_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


probe = Path(sys.argv[1]).absolute()
result = subprocess.run([str(probe)], capture_output=True, preexec_fn=disable_core,
                        env={"PATH": "", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"})
require(result.returncode == -signal.SIGABRT, "original panic aborts child with SIGABRT")
require(b"Crash from within Rust code." in result.stderr, "panic reaches original Rust crash site")

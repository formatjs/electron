"""Generators execute on BB Linux x64 regardless of target platform."""

from pathlib import Path
import platform
import sys
import sysconfig

if sys.platform != 'linux' or platform.machine() != 'x86_64' or sysconfig.get_platform() != 'linux-x86_64':
    raise RuntimeError('Generator Python must match the BB Linux x64 execution platform')
Path(sys.argv[1]).write_text('EXECUTION_PYTHON_OK\n')

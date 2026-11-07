# SPDX-License-Identifier: MIT
"""Materialize original GN copy outputs without ambient execution tools."""

from pathlib import Path
import sys

if len(sys.argv) % 2 != 1:
    raise ValueError("Expected source/output pairs")
for source, output in zip(sys.argv[1::2], sys.argv[2::2]):
    Path(output).write_bytes(Path(source).read_bytes())

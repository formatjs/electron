# SPDX-License-Identifier: MIT
"""Run declared upstream Python generator with pinned Python interpreter."""
import runpy
import sys

script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")

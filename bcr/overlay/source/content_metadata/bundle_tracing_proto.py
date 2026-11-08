# SPDX-License-Identifier: MIT
"""Bundle original generated tracing bindings with declared execution tooling."""

import subprocess
import sys

subprocess.run([
    sys.argv[1], sys.argv[2], "--bundle", "--platform=browser", "--format=esm",
    "--target=es2022", "--minify", "--legal-comments=none", "--log-level=error",
    "--outfile=" + sys.argv[3],
], check=True)

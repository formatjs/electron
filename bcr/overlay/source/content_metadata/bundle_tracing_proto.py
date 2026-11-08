# SPDX-License-Identifier: MIT
"""Bundle original generated tracing bindings with declared execution tooling."""

from pathlib import Path
import subprocess
import sys

source = Path(sys.argv[2])
contents = source.read_text()
replacements = {
    quote + "/@bufbuild/protobuf/wire/index.js" + quote:
        quote + "@bufbuild/protobuf/wire" + quote
    for quote in ("'", '"')
}
if sum(contents.count(before) for before in replacements) != 1:
    raise ValueError("Expected one original browser protobuf wire import")
for before, after in replacements.items():
    contents = contents.replace(before, after)
staged = source.with_suffix(".bundle.ts")
staged.write_text(contents)

subprocess.run([
    sys.argv[1], str(staged), "--bundle", "--platform=browser", "--format=esm",
    "--target=es2022", "--minify", "--legal-comments=none", "--log-level=error",
    "--outfile=" + sys.argv[3],
], check=True)

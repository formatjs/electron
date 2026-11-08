Original Chromium credits, with distribution settings rather than the GN
development sample. The content WebUI GRIT producer consumes this HTML too.

`tools/capture_credits.py --source-root /path/to/patched/chromium` records original
directory discovery, parsed metadata and input hashes without generating HTML.
Use `--vendor original/path` for each path in the current inventory's
`vendored_files`; those verbatim inputs live in `source/license_data`.

The current closure has 766 directories, 706 valid metadata records and 466
shipped entries. Its 1,391 inputs include scanner imports, templates, license
texts, metadata and Chromium DEPS. Existing pinned source repositories supply
1,361 files; 30 license/metadata files come from the checked-in blobs. Revision
and hash guards reject stale captures.

The Bazel action uses the original generator and captured arguments. Empty
declared marker files preserve discovery of directories without metadata.
It runs with declared Python, empty PATH and no GN subprocess. The generic
source runner compares HTML bytes across two private roots and changed mtimes.
`credits_test` checks every shipped dependency's name, URL and complete license
text in the generated page.

Local action analysis passed; hosted generation and test remain pending.

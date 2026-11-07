# Electron registry entry

Layout follows [perplexityai/rocksdb](https://github.com/perplexityai/rocksdb/tree/3cb9c5b1715f2c8cfeaf196facad80aa7b9a1ee5/bcr):

- `MODULE.bazel`: consumer dependencies and exact Electron source extensions.
- `overlay/`: BUILD/Starlark files, generators and captured native source inputs
  projected onto the upstream Electron archive.
- `source.json`: archive URL, strip prefix and integrity.
- `metadata.json`: proposed versions and maintainers.
- `presubmit.yml`: anonymous archive check and isolated source-build consumer.

`tools/stage_bcr_entry.py` stamps the blank module version, computes integrity
for every overlay file and stages `modules/electron/<version>/`. Existing target
versions stay immutable. Electron dependency patches remain in their upstream
ordered stacks; this overlay currently has no additional `bcr/patches` directory.

No module has been published. Maintainers: `longlho` and `formatjsproject`.
The source-component presubmit does not claim a complete Electron runtime build.

#!/usr/bin/env bash
# Fetch byte-identical BCR inputs directly; Bazel verifies their integrity again.
set -euo pipefail
bootstrap_directory="$1"
mkdir -p "$bootstrap_directory"
curl --silent --show-error --fail --location --retry 3 --retry-all-errors --connect-timeout 30 --max-time 180 \
  https://codeload.github.com/bazel-contrib/rules_python/tar.gz/refs/tags/1.9.0 \
  --output "$bootstrap_directory/rules_python-1.9.0.tar.gz"
curl --silent --show-error --fail --location --retry 3 --retry-all-errors --connect-timeout 30 --max-time 180 \
  https://codeload.github.com/bazel-contrib/bazel_features/tar.gz/refs/tags/v1.50.0 \
  --output "$bootstrap_directory/bazel_features-v1.50.0.tar.gz"
curl --silent --show-error --fail --location --retry 3 --retry-all-errors --connect-timeout 30 --max-time 180 \
  https://codeload.github.com/electron/electron/tar.gz/refs/tags/v39.0.0 \
  --output "$bootstrap_directory/v39.0.0.tar.gz"
(
  cd "$bootstrap_directory"
  sha256sum --check <<'HASHES'
098ba13578e796c00c853a2161f382647f32eb9a77099e1c88bc5299333d0d6e  rules_python-1.9.0.tar.gz
094367e732ece23f334eaf84089a720b861d053beeba6a6a68356d3aee1dc32b  bazel_features-v1.50.0.tar.gz
99ea4a5a0b2c1a8182f478cf603209a996007ea402934cb20132fae6475604d9  v39.0.0.tar.gz
HASHES
)

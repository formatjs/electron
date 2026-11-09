// SPDX-License-Identifier: MIT
extern int gn_source_set_constructor_count;
namespace {
struct Initialize {
  Initialize() { ++gn_source_set_constructor_count; }
} initializer;
}  // namespace

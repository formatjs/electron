// SPDX-License-Identifier: MIT
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <vector>

#include "third_party/blink/renderer/platform/fonts/opentype/format_check.rs.h"

namespace {
void Require(bool condition, const char* check) {
  if (!condition) {
    std::fprintf(stderr, "check failed: blink_font %s\n", check);
    std::exit(1);
  }
}

uint32_t Flags(const uint8_t* bytes, size_t size) {
  auto info = font_format_check::get_font_format_info(
      rust::Slice<const uint8_t>(bytes, size));
  return uint32_t{font_format_check::is_colrv0(*info)} |
         (uint32_t{font_format_check::is_colrv1(*info)} << 1) |
         (uint32_t{font_format_check::is_variable(*info)} << 2) |
         (uint32_t{font_format_check::is_sbix(*info)} << 3) |
         (uint32_t{font_format_check::is_cbdt_cblc(*info)} << 4) |
         (uint32_t{font_format_check::is_cff2(*info)} << 5) |
         (uint32_t{font_format_check::is_avar2(*info)} << 6);
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 15, "seven declared SFNT fixtures and expected flag masks");
  const uint8_t invalid[] = {0, 1, 0, 0, 0, 5, 0, 0};
  Require(Flags(invalid, 0) == 0, "empty input has no font flags");
  Require(Flags(invalid, sizeof(invalid)) == 0, "truncated directory has no font flags");
  for (int index = 1; index < argc; index += 2) {
    std::ifstream file(argv[index], std::ios::binary);
    Require(file.is_open(), "declared font fixture available");
    const std::vector<uint8_t> data{std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
    Require(!data.empty(), "font fixture contains source bytes");
    const auto expected = std::strtoul(argv[index + 1], nullptr, 10);
    Require(Flags(data.data(), data.size()) == expected,
            "original font format flags match independent fixture properties");
    Require(Flags(data.data(), 7) == 0, "truncated font rejects partial header");
  }
}

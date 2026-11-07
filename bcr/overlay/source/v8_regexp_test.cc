// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <string>

#include "src/regexp/special-case.h"
#include "unicode/udata.h"

namespace {
using v8::internal::RegExpCaseFolding;

void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: %s\n", message);
    std::exit(1);
  }
}

bool LegacyMatches(UChar32 pattern, UChar32 input) {
  if (RegExpCaseFolding::IgnoreSet().contains(pattern)) return pattern == input;
  icu::UnicodeSet equivalent(pattern, pattern);
  equivalent.closeOver(USET_CASE_INSENSITIVE);
  equivalent.removeAll(RegExpCaseFolding::IgnoreSet());
  return equivalent.contains(input);
}

std::string Read(const char* path) {
  std::ifstream file(path, std::ios::binary);
  Require(file.good(), "regexp generated file readable");
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 3, "regexp generated file arguments");
  const auto source = Read(argv[1]);
  Require(!source.empty() && source == Read(argv[2]), "regexp generation path reproducibility");
  UErrorCode status = U_ZERO_ERROR;
  udata_setFileAccess(UDATA_NO_FILES, &status);
  Require(U_SUCCESS(status), "regexp ambient data access disabled");

  const auto& ignore = RegExpCaseFolding::IgnoreSet();
  const auto& special = RegExpCaseFolding::SpecialAddSet();
  Require(ignore.contains(0x212a) && special.contains('k') && special.contains('K'), "regexp Kelvin tables");
  Require(ignore.contains(0x017f) && special.contains('s') && special.contains('S'), "regexp long s tables");
  Require(ignore.contains(0x00df) && ignore.contains(0x1e9e), "regexp sharp s tables");
  Require(!ignore.containsSome(0xd800, 0xdfff) && !special.containsSome(0xd800, 0xdfff), "regexp surrogate exclusion");

  icu::UnicodeSet unicode('k', 'k');
  unicode.closeOver(USET_CASE_INSENSITIVE);
  Require(unicode.contains(0x212a), "regexp ICU Unicode closure");
  Require(LegacyMatches('k', 'K') && !LegacyMatches('k', 0x212a) && !LegacyMatches(0x212a, 'k'), "regexp Kelvin matching");
  Require(LegacyMatches('s', 'S') && !LegacyMatches('s', 0x017f) && !LegacyMatches(0x017f, 's'), "regexp long s matching");
  Require(LegacyMatches(0x00df, 0x00df) && !LegacyMatches(0x00df, 0x1e9e) && !LegacyMatches(0x1e9e, 0x00df), "regexp sharp s matching");
  Require(LegacyMatches(0x00b5, 0x03bc) && LegacyMatches(0x00b5, 0x039c), "regexp Greek mu matching");
  Require(LegacyMatches('a', 'A') && !LegacyMatches('a', 'b'), "regexp ordinary matching");
  Require(RegExpCaseFolding::Canonicalize(0x00df) == 0x00df &&
              RegExpCaseFolding::Canonicalize(0x017f) == 0x017f &&
              RegExpCaseFolding::Canonicalize(0xd800) == 0xd800 &&
              RegExpCaseFolding::Canonicalize(0xdfff) == 0xdfff,
          "regexp canonicalization boundaries");
  return 0;
}

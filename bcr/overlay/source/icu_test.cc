// SPDX-License-Identifier: MIT
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>

#include "unicode/ubrk.h"
#include "unicode/uclean.h"
#include "unicode/ucol.h"
#include "unicode/udata.h"
#include "unicode/unorm2.h"
#include "unicode/unum.h"
#include "unicode/stringoptions.h"
#include "unicode/ustring.h"
#include "unicode/uversion.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: %s\n", message);
    std::exit(1);
  }
}

void CheckUnicode() {
  UErrorCode status = U_ZERO_ERROR;
  const auto* nfc = unorm2_getNFCInstance(&status);
  UChar output[64] = {};
  Require(U_SUCCESS(status) && nfc, "ICU normalization data");
  const int32_t length = unorm2_normalize(nfc, u"e\u0301", 2, output, 64, &status);
  Require(U_SUCCESS(status) && length == 1 && output[0] == u'\u00e9', "ICU NFC composition");

  status = U_ZERO_ERROR;
  const int32_t required = u_strFoldCase(nullptr, 0, u"I\u0130", 2, U_FOLD_CASE_DEFAULT, &status);
  Require(required == 3 && status == U_BUFFER_OVERFLOW_ERROR, "ICU case fold preflight");
  status = U_ZERO_ERROR;
  const int32_t folded = u_strFoldCase(output, 64, u"I\u0130", 2, U_FOLD_CASE_DEFAULT, &status);
  Require(U_SUCCESS(status) && folded == 3 && u_strncmp(output, u"ii\u0307", 3) == 0, "ICU Unicode case fold");
}

void CheckLocale() {
  UErrorCode status = U_ZERO_ERROR;
  UCollator* collator = ucol_open("fr_FR", &status);
  Require(U_SUCCESS(status) && collator, "ICU collation data");
  ucol_setStrength(collator, UCOL_PRIMARY);
  Require(ucol_strcoll(collator, u"e", 1, u"\u00e9", 1) == UCOL_EQUAL, "ICU primary collation");
  ucol_setStrength(collator, UCOL_TERTIARY);
  Require(ucol_strcoll(collator, u"e", 1, u"\u00e9", 1) == UCOL_LESS, "ICU tertiary collation");
  ucol_close(collator);

  status = U_ZERO_ERROR;
  UNumberFormat* number = unum_open(UNUM_DECIMAL, nullptr, 0, "fr_FR", nullptr, &status);
  Require(U_SUCCESS(status) && number, "ICU number locale data");
  UChar output[64] = {};
  const int32_t length = unum_formatDouble(number, 1234.5, output, 64, nullptr, &status);
  Require(U_SUCCESS(status) && length == 7 && u_strncmp(output, u"1\u202f234,5", 7) == 0, "ICU French number formatting");
  unum_close(number);

  status = U_ZERO_ERROR;
  UBreakIterator* words = ubrk_open(UBRK_WORD, "en_US", u"example.com", 11, &status);
  Require(U_SUCCESS(status) && words, "ICU word break data");
  std::vector<int32_t> boundaries;
  for (int32_t end = ubrk_first(words); (end = ubrk_next(words)) != UBRK_DONE;) {
    boundaries.push_back(end);
  }
  ubrk_close(words);
  Require(boundaries == std::vector<int32_t>({7, 8, 11}), "ICU Chromium word boundaries");
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 2, "ICU declared data argument");
  UErrorCode status = U_ZERO_ERROR;
  udata_setFileAccess(UDATA_NO_FILES, &status);
  Require(U_SUCCESS(status), "ICU ambient file access disabled");
  alignas(16) const unsigned char invalid[64] = {};
  udata_setCommonData(invalid, &status);
  Require(status == U_INVALID_FORMAT_ERROR, "ICU corrupt data rejected");

  std::ifstream input(argv[1], std::ios::binary | std::ios::ate);
  Require(input.good(), "ICU declared data readable");
  const auto bytes = input.tellg();
  Require(bytes > 0 && bytes <= 64 * 1024 * 1024, "ICU declared data size");
  std::vector<std::max_align_t> data((static_cast<size_t>(bytes) + sizeof(std::max_align_t) - 1) / sizeof(std::max_align_t));
  input.seekg(0);
  Require(static_cast<bool>(input.read(reinterpret_cast<char*>(data.data()), bytes)), "ICU declared data complete");
  status = U_ZERO_ERROR;
  udata_setCommonData(data.data(), &status);
  u_init(&status);
  Require(U_SUCCESS(status), "ICU declared data initialization");
  UVersionInfo version;
  u_getVersion(version);
  Require(version[0] == 74 && version[1] == 2, "ICU pinned version");
  CheckUnicode();
  CheckLocale();
  u_cleanup();
  return 0;
}

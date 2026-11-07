// SPDX-License-Identifier: MIT
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <system_error>
#include <vector>

#include "dragonbox/dragonbox.h"
#include "fast_float/fast_float.h"
#include "hwy/aligned_allocator.h"
#include "hwy/targets.h"
#include "simdutf.h"
#include "third_party/zlib/google/compression_utils_portable.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: V8 support %s\n", message);
    std::exit(1);
  }
}

void CheckNumbers() {
  for (double value : {0.1, -1.25, 1234567890.1234567,
                       std::numeric_limits<double>::denorm_min(),
                       std::numeric_limits<double>::min(),
                       std::numeric_limits<double>::max()}) {
    const auto decimal = jkj::dragonbox::to_decimal(value);
    const std::string text = (decimal.is_negative ? "-" : "") +
        std::to_string(decimal.significand) + "e" + std::to_string(decimal.exponent);
    double parsed = 0;
    const auto result = fast_float::from_chars(text.data(), text.data() + text.size(), parsed);
    Require(result.ec == std::errc{} && result.ptr == text.data() + text.size() &&
                std::bit_cast<uint64_t>(parsed) == std::bit_cast<uint64_t>(value),
            "number roundtrip");
  }
  double parsed = 0;
  const std::string overflow = "1e9999";
  Require(fast_float::from_chars(overflow.data(), overflow.data() + overflow.size(), parsed).ec == std::errc::result_out_of_range,
          "number overflow rejected");
  const std::string invalid = "x12";
  const auto result = fast_float::from_chars(invalid.data(), invalid.data() + invalid.size(), parsed);
  Require(result.ec == std::errc::invalid_argument && result.ptr == invalid.data(), "number invalid input rejected");
}

void CheckUnicode() {
  const std::string text = "A\xc3\xa9\xf0\x9f\x98\x80";
  Require(simdutf::validate_utf8(text.data(), text.size()), "UTF8 validation");
  std::vector<char16_t> utf16(simdutf::utf16_length_from_utf8(text.data(), text.size()));
  Require(simdutf::convert_utf8_to_utf16(text.data(), text.size(), utf16.data()) == 4 &&
              utf16 == std::vector<char16_t>{0x41, 0xe9, 0xd83d, 0xde00},
          "UTF16 conversion");
  std::string restored(simdutf::utf8_length_from_utf16(utf16.data(), utf16.size()), '\0');
  Require(simdutf::convert_utf16_to_utf8(utf16.data(), utf16.size(), restored.data()) == text.size() && restored == text,
          "Unicode roundtrip");
  for (const std::string invalid : {std::string("\xc0\xaf", 2), std::string("\xed\xa0\x80", 3), std::string("\xf0\x9f", 2)}) {
    Require(!simdutf::validate_utf8(invalid.data(), invalid.size()), "invalid UTF8 rejected");
  }
}

void CheckHighway() {
  Require(hwy::SupportedTargets() != 0, "CPU target discovery");
  auto* memory = static_cast<unsigned char*>(hwy::AllocateAlignedBytes(4097));
  Require(memory && hwy::IsAligned(memory), "SIMD aligned allocation");
  for (size_t index = 0; index < 4097; ++index) memory[index] = static_cast<unsigned char>(index * 13);
  for (size_t index = 0; index < 4097; ++index) Require(memory[index] == static_cast<unsigned char>(index * 13), "SIMD allocated bytes");
  hwy::FreeAlignedBytes(memory, nullptr, nullptr);
}

void CheckCompression() {
  std::string input(262144, '\0');
  for (size_t index = 0; index < input.size(); ++index) input[index] = static_cast<char>((index * 7 + index / 251) % 256);
  for (auto wrapper : {zlib_internal::ZLIB, zlib_internal::GZIP, zlib_internal::ZRAW}) {
    std::vector<Bytef> compressed(zlib_internal::GzipExpectedCompressedSize(input.size()));
    uLongf size = compressed.size();
    Require(zlib_internal::CompressHelper(wrapper, compressed.data(), &size,
                reinterpret_cast<const Bytef*>(input.data()), input.size(), 6, std::malloc, std::free) == Z_OK && size < input.size(),
            "compression");
    std::string restored(input.size(), '\0');
    uLongf restored_size = restored.size();
    Require(zlib_internal::UncompressHelper(wrapper, reinterpret_cast<Bytef*>(restored.data()), &restored_size,
                compressed.data(), size) == Z_OK && restored_size == input.size() && restored == input,
            "compression roundtrip");
    restored_size = 8;
    Require(zlib_internal::UncompressHelper(wrapper, reinterpret_cast<Bytef*>(restored.data()), &restored_size,
                compressed.data(), size) != Z_OK, "short output rejected");
    if (wrapper != zlib_internal::ZRAW) {
      compressed[size / 2] ^= 0x40;
      restored_size = restored.size();
      Require(zlib_internal::UncompressHelper(wrapper, reinterpret_cast<Bytef*>(restored.data()), &restored_size,
                  compressed.data(), size) != Z_OK, "corrupt compression rejected");
    }
  }
  const auto* bytes = reinterpret_cast<const Bytef*>("123456789");
  Require(crc32(0, bytes, 9) == 0xcbf43926UL && adler32(1, bytes, 9) == 0x091e01deUL, "checksum vectors");
}
}  // namespace

int main() {
  CheckNumbers();
  CheckUnicode();
  CheckHighway();
  CheckCompression();
  return 0;
}

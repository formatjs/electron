// SPDX-License-Identifier: MIT
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "base/at_exit.h"
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/files/memory_mapped_file.h"
#include "base/i18n/icu_util.h"
#include "include/codec/SkPngRustDecoder.h"
#include "include/core/SkBitmap.h"
#include "include/core/SkCanvas.h"
#include "include/core/SkData.h"
#include "include/core/SkFont.h"
#include "include/core/SkFontArguments.h"
#include "include/core/SkPaint.h"
#include "include/core/SkPath.h"
#include "include/core/SkPixmap.h"
#include "include/core/SkShader.h"
#include "include/core/SkStream.h"
#include "include/core/SkSurface.h"
#include "include/effects/SkRuntimeEffect.h"
#include "include/encode/SkPngRustEncoder.h"
#include "include/ports/SkTypeface_fontations.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: skia %s\n", message);
    std::exit(1);
  }
}

void CheckRasterAndShader() {
  auto surface = SkSurfaces::Raster(SkImageInfo::MakeN32Premul(16, 16));
  Require(surface != nullptr, "native raster surface");
  surface->getCanvas()->clear(SK_ColorRED);
  auto compiled = SkRuntimeEffect::MakeForShader(SkString("half4 main(float2 p) { return half4(0, 1, 0, 1); }"));
  Require(compiled.effect != nullptr, "original SkSL compilation");
  SkRuntimeShaderBuilder builder(compiled.effect);
  SkPaint paint;
  paint.setShader(builder.makeShader());
  Require(paint.getShader() != nullptr, "native runtime shader");
  surface->getCanvas()->drawRect(SkRect::MakeXYWH(4, 4, 8, 8), paint);
  SkBitmap pixels;
  pixels.allocN32Pixels(16, 16);
  Require(surface->readPixels(pixels, 0, 0), "raster pixel readback");
  for (int y = 0; y < 16; ++y)
    for (int x = 0; x < 16; ++x)
      Require(pixels.getColor(x, y) == ((x >= 4 && x < 12 && y >= 4 && y < 12) ? SK_ColorGREEN : SK_ColorRED), "SkSL raster pixel vector");
  auto rejected = SkRuntimeEffect::MakeForShader(SkString("half4 main(float2 p) { return missing_symbol; }"));
  Require(!rejected.effect && !rejected.errorText.isEmpty(), "invalid SkSL rejection");
}

void CheckRustPng() {
  constexpr std::array<uint8_t, 16> pixels = {1, 2, 3, 255, 4, 5, 6, 127, 0, 0, 0, 0, 200, 177, 31, 255};
  const auto info = SkImageInfo::Make(2, 2, kRGBA_8888_SkColorType, kUnpremul_SkAlphaType);
  SkPixmap source(info, pixels.data(), 8);
  SkDynamicMemoryWStream stream;
  Require(SkPngRustEncoder::Encode(&stream, source, {}), "original Rust PNG encoding");
  auto encoded = stream.detachAsData();
  Require(encoded && SkPngRustDecoder::IsPng(encoded->data(), encoded->size()), "Rust PNG signature");
  SkCodec::Result result;
  auto decoder = SkPngRustDecoder::Decode(SkMemoryStream::Make(encoded), &result);
  Require(decoder && result == SkCodec::kSuccess && decoder->dimensions() == SkISize::Make(2, 2), "original Rust PNG decoding");
  std::array<uint8_t, 16> decoded;
  Require(decoder->getPixels(info, decoded.data(), 8) == SkCodec::kSuccess && decoded == pixels, "Rust PNG RGBA alpha roundtrip");
  constexpr char invalid[] = "invalid png";
  auto rejected = SkPngRustDecoder::Decode(SkMemoryStream::MakeCopy(invalid, sizeof(invalid)), &result);
  Require(!rejected && result != SkCodec::kSuccess, "invalid Rust PNG rejection");
}

void CheckFontations(const char* path) {
  auto bytes = SkData::MakeFromFileName(path);
  Require(bytes != nullptr, "declared Skia font bytes");
  auto typeface = SkTypeface_Make_Fontations(bytes, SkFontArguments{});
  Require(typeface && typeface->countGlyphs() > 0, "original Skia fontations typeface");
  SkFont font(typeface, 32);
  const auto glyph = font.unicharToGlyph('f');
  Require(glyph != 0, "Rust font glyph mapping");
  auto outline = font.getPath(glyph);
  Require(outline && !outline->isEmpty() && !outline->getBounds().isEmpty(), "Rust CXX glyph path bridge");
  constexpr char invalid[] = "invalid font";
  Require(!SkTypeface_Make_Fontations(SkData::MakeWithCopy(invalid, sizeof(invalid)), SkFontArguments{}), "invalid Skia font rejection");
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 3, "declared ICU and font arguments");
  base::AtExitManager at_exit;
  base::File data(base::MakeAbsoluteFilePath(base::FilePath(argv[1])), base::File::FLAG_OPEN | base::File::FLAG_READ);
  Require(data.IsValid() && base::i18n::InitializeICUWithFileDescriptor(data.TakePlatformFile(), base::MemoryMappedFile::Region::kWholeFile), "declared ICU initialization");
  CheckRasterAndShader();
  CheckRustPng();
  CheckFontations(argv[2]);
}

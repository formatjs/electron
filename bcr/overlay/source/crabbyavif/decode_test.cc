// SPDX-License-Identifier: MIT
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

#include "dav1d/dav1d.h"
#include "libyuv/version.h"
#include "third_party/libpng/png.h"
#include "third_party/crabbyavif/src/include/avif/avif.h"

namespace {
using namespace crabbyavif;

void Require(bool condition, const char* check) {
  if (!condition) {
    std::fprintf(stderr, "check failed: crabby_decode %s\n", check);
    std::exit(1);
  }
}

void CheckConversion() {
  auto* image = crabby_avifImageCreate(2, 2, 8, AVIF_PIXEL_FORMAT_YUV420);
  Require(image != nullptr, "C API allocates conversion image");
  image->yuvRange = AVIF_RANGE_LIMITED;
  image->matrixCoefficients = AVIF_MATRIX_COEFFICIENTS_BT601;
  uint8_t pixels[] = {255, 0, 0, 255, 255, 0, 0, 255,
                      255, 0, 0, 255, 255, 0, 0, 255};
  avifRGBImage rgb{};
  crabby_avifRGBImageSetDefaults(&rgb, image);
  rgb.format = AVIF_RGB_FORMAT_RGBA;
  rgb.pixels = pixels;
  rgb.rowBytes = 8;
  Require(crabby_avifImageRGBToYUV(image, &rgb) == AVIF_RESULT_OK,
          "original Rust RGB conversion succeeds");
  Require(image->yuvPlanes[0] && image->yuvPlanes[1] && image->yuvPlanes[2],
          "C API owns converted YUV planes");
  for (unsigned y = 0; y < 2; ++y)
    for (unsigned x = 0; x < 2; ++x)
      Require(std::abs(int(image->yuvPlanes[0][y * image->yuvRowBytes[0] + x]) - 82) <= 1,
              "red conversion has BT601 limited luma");
  Require(std::abs(int(image->yuvPlanes[1][0]) - 90) <= 1 &&
              std::abs(int(image->yuvPlanes[2][0]) - 240) <= 1,
          "red conversion has BT601 limited chroma");
  crabby_avifImageDestroy(image);
}
}  // namespace

int main(int argc, char** argv) {
  using namespace crabbyavif;
  Require(argc == 3, "declared AVIF and independent PNG fixtures");
  char versions[256]{};
  crabby_avifCodecVersions(versions);
  Require(std::strstr(versions, "dav1d") && std::strstr(versions, dav1d_version()),
          "Rust decoder reports matching native dav1d version");
  Require(crabby_avifLibYUVVersion() == LIBYUV_VERSION,
          "generated libyuv binding matches source headers");

  auto* bad_decoder = crabby_avifDecoderCreate();
  auto* bad_image = crabby_avifImageCreateEmpty();
  Require(bad_decoder && bad_image, "C API allocates error case objects");
  const uint8_t invalid[] = {0, 1, 2, 3};
  Require(crabby_avifDecoderReadMemory(bad_decoder, bad_image, invalid, sizeof(invalid)) != AVIF_RESULT_OK,
          "malformed AVIF returns an error across Rust FFI");
  crabby_avifImageDestroy(bad_image);
  crabby_avifDecoderDestroy(bad_decoder);

  std::ifstream input(argv[1], std::ios::binary);
  Require(input.is_open(), "declared AVIF fixture available");
  const std::vector<uint8_t> encoded{std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
  auto* decoder = crabby_avifDecoderCreate();
  auto* image = crabby_avifImageCreateEmpty();
  Require(decoder && image, "C API allocates decoder objects");
  decoder->maxThreads = 1;
  Require(crabby_avifDecoderReadMemory(decoder, image, encoded.data(), encoded.size()) == AVIF_RESULT_OK,
          "original Rust decoder reads lossless AVIF through native dav1d");

  FILE* reference = std::fopen(argv[2], "rb");
  Require(reference != nullptr, "declared PNG reference available");
  png_structp png = png_create_read_struct(PNG_LIBPNG_VER_STRING, nullptr, nullptr, nullptr);
  png_infop info = png ? png_create_info_struct(png) : nullptr;
  std::vector<uint8_t> expected;
  std::vector<png_bytep> rows;
  Require(png && info, "source libpng allocates reference reader");
  Require(setjmp(png_jmpbuf(png)) == 0, "source libpng reads independent reference");
  png_init_io(png, reference);
  png_read_info(png, info);
  const auto width = png_get_image_width(png, info);
  const auto height = png_get_image_height(png, info);
  Require(width == 403 && height == 302 && png_get_bit_depth(png, info) == 8 &&
              png_get_color_type(png, info) == PNG_COLOR_TYPE_RGB,
          "independent reference is original RGB8 image");
  expected.resize(width * height * 3);
  for (unsigned y = 0; y < height; ++y)
    rows.push_back(expected.data() + y * width * 3);
  png_read_image(png, rows.data());
  png_destroy_read_struct(&png, &info, nullptr);
  std::fclose(reference);
  Require(image->width == width && image->height == height && image->depth == 8,
          "decoded AVIF dimensions and depth match reference");
  avifRGBImage rgb{};
  crabby_avifRGBImageSetDefaults(&rgb, image);
  rgb.format = AVIF_RGB_FORMAT_RGB;
  rgb.depth = 8;
  rgb.maxThreads = 1;
  Require(crabby_avifRGBImageAllocatePixels(&rgb) == AVIF_RESULT_OK,
          "C API allocates RGB output");
  Require(crabby_avifImageYUVToRGB(image, &rgb) == AVIF_RESULT_OK,
          "original Rust image conversion succeeds");
  Require(rgb.pixels && rgb.rowBytes >= width * 3, "RGB output has bounded row layout");
  for (unsigned y = 0; y < height; ++y)
    Require(std::memcmp(rgb.pixels + y * rgb.rowBytes, expected.data() + y * width * 3, width * 3) == 0,
            "every decoded RGB byte matches independent lossless PNG");
  crabby_avifRGBImageFreePixels(&rgb);
  crabby_avifImageDestroy(image);
  crabby_avifDecoderDestroy(decoder);
  CheckConversion();
}

// SPDX-License-Identifier: MIT
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "third_party/libjpeg_turbo/src/jpeglib.h"
extern "C" {
#include "third_party/libjpeg_turbo/src/jsimd.h"
}
#include "third_party/libwebp/src/src/webp/decode.h"
#include "third_party/libwebp/src/src/webp/encode.h"
#include "third_party/wuffs/src/release/c/wuffs-v0.3.c"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: codecs %s\n", message);
    std::exit(1);
  }
}

void CheckJpeg() {
  Require(jsimd_can_rgb_ycc() != 0, "native JPEG SIMD dispatch");
  jpeg_error_mgr errors;
  jpeg_compress_struct encoder{};
  encoder.err = jpeg_std_error(&errors);
  jpeg_create_compress(&encoder);
  unsigned char* encoded = nullptr;
  unsigned long size = 0;
  jpeg_mem_dest(&encoder, &encoded, &size);
  encoder.image_width = 32;
  encoder.image_height = 32;
  encoder.input_components = 3;
  encoder.in_color_space = JCS_RGB;
  jpeg_set_defaults(&encoder);
  jpeg_set_quality(&encoder, 95, TRUE);
  jpeg_start_compress(&encoder, TRUE);
  std::array<unsigned char, 96> row;
  for (size_t x = 0; x < 32; ++x) {
    row[x * 3] = 40;
    row[x * 3 + 1] = 90;
    row[x * 3 + 2] = 170;
  }
  JSAMPROW scanline = row.data();
  while (encoder.next_scanline < encoder.image_height)
    Require(jpeg_write_scanlines(&encoder, &scanline, 1) == 1, "JPEG scanline encoding");
  jpeg_finish_compress(&encoder);
  jpeg_destroy_compress(&encoder);
  Require(size > 2 && encoded[0] == 0xff && encoded[1] == 0xd8, "JPEG encoded stream");
  jpeg_decompress_struct decoder{};
  decoder.err = jpeg_std_error(&errors);
  jpeg_create_decompress(&decoder);
  jpeg_mem_src(&decoder, encoded, size);
  Require(jpeg_read_header(&decoder, TRUE) == JPEG_HEADER_OK, "JPEG header decoding");
  decoder.out_color_space = JCS_RGB;
  Require(jpeg_start_decompress(&decoder) && decoder.output_width == 32 && decoder.output_height == 32 && decoder.output_components == 3, "JPEG decoded dimensions");
  while (decoder.output_scanline < decoder.output_height) {
    Require(jpeg_read_scanlines(&decoder, &scanline, 1) == 1, "JPEG scanline decoding");
    for (size_t x = 0; x < 32; ++x)
      Require(std::abs(int(row[x * 3]) - 40) <= 3 && std::abs(int(row[x * 3 + 1]) - 90) <= 3 && std::abs(int(row[x * 3 + 2]) - 170) <= 3, "JPEG decoded color tolerance");
  }
  Require(jpeg_finish_decompress(&decoder), "JPEG decoder completion");
  jpeg_destroy_decompress(&decoder);
  std::free(encoded);
}

void CheckWebp() {
  constexpr std::array<uint8_t, 16> pixels = {1, 2, 3, 255, 4, 5, 6, 127, 0, 0, 0, 0, 200, 177, 31, 255};
  uint8_t* encoded = nullptr;
  size_t size = WebPEncodeLosslessRGBA(pixels.data(), 2, 2, 8, &encoded);
  Require(size > 12 && encoded, "WebP lossless encoding");
  int width, height;
  Require(WebPGetInfo(encoded, size, &width, &height) && width == 2 && height == 2, "WebP encoded dimensions");
  uint8_t* decoded = WebPDecodeRGBA(encoded, size, &width, &height);
  Require(decoded && width == 2 && height == 2 && std::memcmp(decoded, pixels.data(), pixels.size()) == 0, "WebP RGBA alpha roundtrip");
  WebPFree(decoded);
  encoded[0] ^= 1;
  Require(!WebPGetInfo(encoded, size, &width, &height) && WebPDecodeRGBA(encoded, size, &width, &height) == nullptr, "invalid WebP rejection");
  WebPFree(encoded);
}

void CheckGif() {
  std::array<uint8_t, 35> encoded = {'G', 'I', 'F', '8', '9', 'a', 1, 0, 1, 0, 0x80, 0, 0, 0, 0, 0, 255, 255, 255, 0x2c, 0, 0, 0, 0, 1, 0, 1, 0, 0, 2, 2, 0x44, 1, 0, 0x3b};
  auto* decoder = wuffs_gif__decoder__alloc();
  Require(decoder != nullptr, "Wuffs GIF decoder allocation");
  auto input = wuffs_base__ptr_u8__reader(encoded.data(), encoded.size(), true);
  wuffs_base__image_config image{};
  auto status = wuffs_gif__decoder__decode_image_config(decoder, &image, &input);
  Require(status.is_ok() && image.pixcfg.width() == 1 && image.pixcfg.height() == 1, "GIF image configuration");
  wuffs_base__frame_config frame{};
  status = wuffs_gif__decoder__decode_frame_config(decoder, &frame, &input);
  Require(status.is_ok(), "GIF frame configuration");
  wuffs_base__pixel_config config{};
  config.set(WUFFS_BASE__PIXEL_FORMAT__BGRA_NONPREMUL, WUFFS_BASE__PIXEL_SUBSAMPLING__NONE, 1, 1);
  std::array<uint8_t, 4> pixel = {19, 23, 31, 47};
  wuffs_base__pixel_buffer buffer{};
  status = buffer.set_from_slice(&config, wuffs_base__make_slice_u8(pixel.data(), pixel.size()));
  Require(status.is_ok(), "GIF pixel buffer");
  const auto needed = wuffs_gif__decoder__workbuf_len(decoder).max_incl;
  Require(needed <= 1024 * 1024, "GIF bounded work buffer");
  std::vector<uint8_t> work(needed);
  status = wuffs_gif__decoder__decode_frame(decoder, &buffer, &input, WUFFS_BASE__PIXEL_BLEND__SRC, wuffs_base__make_slice_u8(work.data(), work.size()), nullptr);
  Require(status.is_ok() && pixel == std::array<uint8_t, 4>{0, 0, 0, 255}, "native GIF pixel decoding");
  status = wuffs_gif__decoder__decode_frame_config(decoder, &frame, &input);
  Require(status.repr == wuffs_base__note__end_of_data, "GIF frame completion");
  std::free(decoder);
  encoded[0] ^= 1;
  decoder = wuffs_gif__decoder__alloc();
  Require(decoder != nullptr, "invalid GIF decoder allocation");
  input = wuffs_base__ptr_u8__reader(encoded.data(), encoded.size(), true);
  status = wuffs_gif__decoder__decode_image_config(decoder, &image, &input);
  Require(status.is_error(), "invalid GIF rejection");
  std::free(decoder);
}
}  // namespace

int main() {
  CheckJpeg();
  CheckWebp();
  CheckGif();
}

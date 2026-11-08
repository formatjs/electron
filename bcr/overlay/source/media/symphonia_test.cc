// SPDX-License-Identifier: MIT
#include <bit>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

#include "media/filters/symphonia_glue.rs.h"

namespace {
void Require(bool condition, const char* check) {
  if (!condition) {
    std::fprintf(stderr, "check failed: symphonia %s\n", check);
    std::exit(1);
  }
}

std::vector<uint8_t> Read(const char* path) {
  std::ifstream file(path, std::ios::binary);
  Require(file.is_open(), "declared audio fixture available");
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}

uint32_t Little32(const uint8_t* data) {
  return uint32_t{data[0]} | (uint32_t{data[1]} << 8) |
         (uint32_t{data[2]} << 16) | (uint32_t{data[3]} << 24);
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 6, "declared fixture and packet bounds");
  const auto encoded = Read(argv[1]);
  const auto reference = Read(argv[2]);
  const auto offset = std::strtoull(argv[3], nullptr, 10);
  const auto size = std::strtoull(argv[4], nullptr, 10);
  const auto frames = std::strtoull(argv[5], nullptr, 10);
  Require(encoded.size() > 42 && std::memcmp(encoded.data(), "fLaC", 4) == 0 &&
              offset < encoded.size() && size <= encoded.size() - offset,
          "original FLAC packet bounds");
  Require(reference.size() > 12 &&
              std::memcmp(reference.data(), "RIFF", 4) == 0 &&
              std::memcmp(reference.data() + 8, "WAVE", 4) == 0,
          "independent WAV reference container");
  std::vector<uint8_t> pcm;
  for (size_t position = 12; position + 8 <= reference.size();) {
    const auto length = Little32(reference.data() + position + 4);
    Require(length <= reference.size() - position - 8,
            "bounded WAV reference chunk");
    if (std::memcmp(reference.data() + position, "data", 4) == 0) {
      pcm.assign(reference.begin() + position + 8,
                 reference.begin() + position + 8 + length);
    }
    position += 8 + length + (length & 1);
  }
  Require(frames > 0 && pcm.size() >= frames * 3,
          "independent 24 bit reference samples");

  media::SymphoniaDecoderConfig config{};
  config.codec = media::SymphoniaAudioCodec::Flac;
  for (size_t index = 8; index < 42; ++index)
    config.extra_data.push_back(encoded[index]);
  auto initialized = media::init_symphonia_decoder(config);
  Require(initialized.status == media::SymphoniaInitStatus::Ok &&
              initialized.error_str.empty(),
          "original Rust decoder initialized through CXX");
  media::SymphoniaPacket packet{};
  for (size_t index = offset; index < offset + size; ++index)
    packet.data.push_back(encoded[index]);
  auto decoded = initialized.decoder->decode(packet);
  Require(decoded.status == media::SymphoniaDecodeStatus::Ok &&
              decoded.buffer->sample_format == media::SymphoniaSampleFormat::S32 &&
              decoded.buffer->sample_rate == 44100 &&
              decoded.buffer->num_frames == frames &&
              decoded.buffer->data.size() == frames * sizeof(int32_t),
          "decoded FLAC frame shape and sample format");
  for (size_t index = 0; index < frames; ++index) {
    int32_t actual;
    std::memcpy(&actual, decoded.buffer->data.data() + index * 4, sizeof(actual));
    const auto packed = uint32_t{pcm[index * 3]} |
                        (uint32_t{pcm[index * 3 + 1]} << 8) |
                        (uint32_t{pcm[index * 3 + 2]} << 16);
    Require(actual == std::bit_cast<int32_t>(packed << 8),
            "lossless decoded samples match independent WAV");
  }

  media::SymphoniaPacket empty{};
  const auto rejected = initialized.decoder->decode(empty);
  Require(rejected.status == media::SymphoniaDecodeStatus::UnexpectedEndOfStream &&
              !rejected.error_str.empty() && rejected.buffer->data.empty(),
          "truncated packet reports Rust error through CXX");
  const auto recovered = initialized.decoder->decode(packet);
  Require(recovered.status == media::SymphoniaDecodeStatus::Ok &&
              recovered.buffer->data.size() == decoded.buffer->data.size() &&
              std::memcmp(recovered.buffer->data.data(), decoded.buffer->data.data(),
                          decoded.buffer->data.size()) == 0,
          "decoder recovers after rejected packet");

  config.codec = static_cast<media::SymphoniaAudioCodec>(37);
  auto invalid = media::init_symphonia_decoder(config);
  Require(invalid.status == media::SymphoniaInitStatus::InvalidConfig &&
              !invalid.error_str.empty(),
          "unsupported codec rejected through CXX");
  const auto invalid_decode = invalid.decoder->decode(packet);
  Require(invalid_decode.status == media::SymphoniaDecodeStatus::InvalidDecoderState &&
              invalid_decode.buffer->data.empty(),
          "failed decoder cannot return audio samples");
  return 0;
}

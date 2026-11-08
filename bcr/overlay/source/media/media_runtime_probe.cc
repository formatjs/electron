// SPDX-License-Identifier: MIT
#include <bit>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "media/base/audio_parameters.h"
extern "C" {
#include "alsa/asoundlib.h"
#include "third_party/ffmpeg/libavcodec/avcodec.h"
#include "third_party/ffmpeg/libavutil/mem.h"
}

namespace {
void Require(bool condition, const char* check) {
  if (!condition) {
    std::fprintf(stderr, "check failed: media_runtime %s\n", check);
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
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  base::FeatureList::InitInstance("", "");
  Require(argc == 6, "declared fixture and packet bounds");
  const auto encoded = Read(argv[1]);
  const auto wave = Read(argv[2]);
  const auto offset = std::strtoull(argv[3], nullptr, 10);
  const auto size = std::strtoull(argv[4], nullptr, 10);
  const auto frames = std::strtoull(argv[5], nullptr, 10);
  Require(encoded.size() > 42 && offset < encoded.size() &&
              size <= encoded.size() - offset,
          "original FLAC frame bounds");
  std::vector<uint8_t> pcm;
  for (size_t position = 12; position + 8 <= wave.size();) {
    const auto length = Little32(wave.data() + position + 4);
    Require(length <= wave.size() - position - 8, "bounded WAV reference chunks");
    if (std::memcmp(wave.data() + position, "data", 4) == 0)
      pcm.assign(wave.begin() + position + 8, wave.begin() + position + 8 + length);
    position += 8 + length + (length & 1);
  }
  Require(frames > 0 && pcm.size() >= frames * 3,
          "independent 24 bit WAV reference");

  Require(avcodec_version() == LIBAVCODEC_VERSION_INT,
          "source FFmpeg runtime matches headers");
  Require(avcodec_find_decoder(AV_CODEC_ID_AAC) &&
              avcodec_find_decoder(AV_CODEC_ID_H264),
          "original Chrome AAC and H264 decoders registered");
  const AVCodec* codec = avcodec_find_decoder(AV_CODEC_ID_FLAC);
  Require(codec != nullptr, "source FFmpeg FLAC decoder available");
  AVCodecContext* context = avcodec_alloc_context3(codec);
  Require(context != nullptr, "source FFmpeg decoder allocation");
  context->extradata_size = 34;
  context->extradata = static_cast<uint8_t*>(av_mallocz(34 + AV_INPUT_BUFFER_PADDING_SIZE));
  Require(context->extradata != nullptr, "source FFmpeg padded metadata allocation");
  std::memcpy(context->extradata, encoded.data() + 8, 34);
  Require(avcodec_open2(context, codec, nullptr) == 0,
          "source FFmpeg decoder opens original stream metadata");
  AVPacket* packet = av_packet_alloc();
  AVFrame* frame = av_frame_alloc();
  Require(packet && frame && av_new_packet(packet, static_cast<int>(size)) == 0,
          "source FFmpeg packet and frame allocation");
  std::memcpy(packet->data, encoded.data() + offset, size);
  Require(avcodec_send_packet(context, packet) == 0 &&
              avcodec_receive_frame(context, frame) == 0,
          "native FFmpeg decodes original FLAC packet");
  Require((frame->format == AV_SAMPLE_FMT_S32 || frame->format == AV_SAMPLE_FMT_S32P) &&
              frame->sample_rate == 44100 && frame->ch_layout.nb_channels == 1 &&
              frame->nb_samples == static_cast<int>(frames),
          "decoded FFmpeg frame shape and sample format");
  for (size_t index = 0; index < frames; ++index) {
    int32_t actual;
    std::memcpy(&actual, frame->data[0] + index * 4, sizeof(actual));
    const auto expected = uint32_t{pcm[index * 3]} |
                          (uint32_t{pcm[index * 3 + 1]} << 8) |
                          (uint32_t{pcm[index * 3 + 2]} << 16);
    Require(actual == std::bit_cast<int32_t>(expected << 8),
            "lossless FFmpeg samples match independent WAV");
  }
  av_frame_free(&frame);
  av_packet_free(&packet);
  avcodec_free_context(&context);

  media::AudioParameters parameters(media::AudioParameters::AUDIO_PCM_LOW_LATENCY,
                                    media::ChannelLayoutConfig::Stereo(), 44100, 441);
  Require(parameters.IsValid() &&
              parameters.GetBytesPerBuffer(media::kSampleFormatS16) == 1764 &&
              parameters.GetBufferDuration().InMicroseconds() == 10000,
          "native Chromium audio buffer layout and duration");
  Require(!media::AudioParameters().IsValid(),
          "unconfigured Chromium audio parameters rejected");
  Require(std::strcmp(snd_asoundlib_version(), SND_LIB_VERSION_STR) == 0,
          "declared ALSA runtime matches SDK version");
  snd_pcm_info_t* info = nullptr;
  Require(snd_pcm_info_malloc(&info) == 0 && info != nullptr,
          "ALSA metadata allocation without audio hardware");
  snd_pcm_info_free(info);
  return 0;
}

// SPDX-License-Identifier: MIT
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "components/viz/common/resources/shared_image_format.h"
#include "gpu/command_buffer/common/buffer.h"
#include "gpu/command_buffer/common/cmd_buffer_common.h"
#include "gpu/command_buffer/service/command_buffer_service.h"
#include "gpu/command_buffer/service/common_decoder.h"
#include "gpu/command_buffer/service/disk_cache_proto.pb.h"
#include "gpu/config/gpu_preferences.h"
#include "gpu/webgpu/dawn_commit_hash.h"

namespace {
void Require(bool condition, const char* check) {
  if (!condition) {
    std::fprintf(stderr, "check failed: gpu_transport %s\n", check);
    std::exit(1);
  }
}

class Client : public gpu::CommandBufferServiceClient {
 public:
  CommandBatchProcessedResult OnCommandBatchProcessed() override {
    return kContinueExecution;
  }
  void OnParseError() override { ++errors; }
  int errors = 0;
};

class Decoder : public gpu::CommonDecoder {
 public:
  using CommonDecoder::CommonDecoder;
  using CommonDecoder::DoCommonCommand;

  template <typename T>
  gpu::error::Error Run(const T& command) {
    return DoCommonCommand(command.header.command, command.header.size - 1,
                           &command);
  }
};
}  // namespace

int main(int argc, char** argv) {
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  Require(argc == 2 && std::strcmp(DAWN_COMMIT_HASH, argv[1]) == 0,
          "declared Dawn source revision");

  Client client;
  gpu::CommandBufferService service(&client, nullptr);
  Decoder decoder(nullptr, &service);
  gpu::cmd::SetToken token;
  token.Init(41);
  Require(decoder.Run(token) == gpu::error::kNoError &&
              service.GetState().token == 41,
          "client token decoded by native service");
  Require(decoder.DoCommonCommand(gpu::cmd::SetToken::kCmdId, 0, &token) ==
              gpu::error::kInvalidArguments,
          "malformed command arity rejected");

  int32_t transfer_id = 0;
  auto buffer = service.CreateTransferBuffer(64, &transfer_id);
  Require(buffer && transfer_id > 0, "native transfer buffer allocation");
  const unsigned char payload[] = {1, 3, 5, 7, 9, 11, 13, 15};
  std::memcpy(static_cast<unsigned char*>(buffer->memory()) + 16,
              payload, sizeof(payload));
  gpu::cmd::SetBucketSize size;
  size.Init(7, sizeof(payload));
  Require(decoder.Run(size) == gpu::error::kNoError,
          "native command bucket allocation");
  gpu::cmd::SetBucketData copy;
  copy.Init(7, 0, sizeof(payload), transfer_id, 16);
  Require(decoder.Run(copy) == gpu::error::kNoError &&
              std::memcmp(decoder.GetBucket(7)->GetData(0, sizeof(payload)),
                          payload, sizeof(payload)) == 0,
          "shared transfer bytes decoded into bucket");
  copy.Init(7, 0, sizeof(payload), transfer_id,
            std::numeric_limits<uint32_t>::max());
  Require(decoder.Run(copy) == gpu::error::kInvalidArguments &&
              std::memcmp(decoder.GetBucket(7)->GetData(0, sizeof(payload)),
                          payload, sizeof(payload)) == 0,
          "overflowing shared range rejected without mutation");
  service.DestroyTransferBuffer(transfer_id);
  copy.Init(7, 0, sizeof(payload), transfer_id, 16);
  Require(decoder.Run(copy) == gpu::error::kInvalidArguments,
          "released transfer handle rejected");
  decoder.set_max_bucket_size(32);
  size.Init(7, 33);
  Require(decoder.Run(size) == gpu::error::kOutOfBounds &&
              decoder.GetBucket(7)->size() == sizeof(payload),
          "bucket limit preserves existing bytes");
  service.SetParseError(gpu::error::kInvalidArguments);
  service.SetParseError(gpu::error::kOutOfBounds);
  Require(client.errors == 1 &&
              service.GetState().error == gpu::error::kInvalidArguments,
          "parse error observer and first error retained");

  gpu::GpuPreferences preferences;
  preferences.use_passthrough_cmd_decoder = true;
  preferences.use_vulkan = gpu::VulkanImplementationName::kSwiftshader;
  preferences.disable_vulkan_surface = true;
  preferences.vulkan_heap_memory_limit = 64;
  gpu::GpuPreferences restored;
  Require(restored.FromSwitchValue(preferences.ToSwitchValue()) &&
              restored.use_passthrough_cmd_decoder &&
              restored.use_vulkan == preferences.use_vulkan &&
              restored.disable_vulkan_surface &&
              restored.vulkan_heap_memory_limit == 64,
          "native GPU preferences IPC roundtrip");
  Require(!restored.FromSwitchValue("invalid-gpu-preferences") &&
              restored.vulkan_heap_memory_limit == 64,
          "invalid GPU preferences preserve state");

  GpuProgramProto program;
  program.set_sha("source-shader");
  program.set_format(7);
  program.set_program(std::string("shader\0bytes", 12));
  program.mutable_vertex_shader()->add_attribs()->mutable_basic()->set_name(
      "position");
  auto wire = program.SerializeAsString();
  GpuProgramProto parsed;
  Require(parsed.ParseFromString(wire) && parsed.program() == program.program() &&
              parsed.vertex_shader().attribs(0).basic().name() == "position",
          "original shader cache protobuf roundtrip");
  wire.pop_back();
  GpuProgramProto truncated;
  Require(!truncated.ParseFromString(wire),
          "truncated shader cache protobuf rejected");

  const auto format = viz::MultiPlaneFormat::kNV12;
  const gfx::Size odd_size(7, 5);
  Require(format.NumberOfPlanes() == 2 &&
              format.GetPlaneSize(0, odd_size) == odd_size &&
              format.GetPlaneSize(1, odd_size) == gfx::Size(4, 3) &&
              format.MaybeEstimatedSizeInBytes(odd_size) == size_t{59},
          "native Viz subsampled plane layout");
  return 0;
}

// SPDX-License-Identifier: MIT
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <string>
#include <string_view>
#include <utility>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/containers/span.h"
#include "base/feature_list.h"
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/files/memory_mapped_file.h"
#include "base/files/scoped_temp_dir.h"
#include "base/i18n/icu_util.h"
#include "base/task/single_thread_task_executor.h"
#include "base/threading/thread.h"
#include "mojo/core/embedder/embedder.h"
#include "mojo/core/embedder/scoped_ipc_support.h"
#include "third_party/libdrm/src/xf86drm.h"
#include "third_party/libdrm/src/include/drm/drm_fourcc.h"
#include "ui/base/resource/data_pack.h"
#include "ui/base/resource/resource_scale_factor.h"
#include "ui/gfx/buffer_format_util.h"
#include "ui/gfx/codec/png_codec.h"
#include "ui/gfx/geometry/mojom/geometry.mojom.h"
#include "ui/gfx/geometry/point_f.h"
#include "ui/gfx/geometry/rect.h"
#include "ui/gfx/geometry/transform.h"
#include "ui/gfx/range/mojom/range.mojom.h"
#include "ui/gfx/range/range.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: gfx %s\n", message);
    std::exit(1);
  }
}

void CheckGeometry() {
  gfx::Transform transform;
  transform.Translate(10, 20);
  transform.Scale(2, 3);
  const auto mapped = transform.MapPoint(gfx::PointF(1, 2));
  Require(mapped == gfx::PointF(12, 26), "native transform composition");
  gfx::Transform inverse;
  Require(transform.GetInverse(&inverse), "native transform inverse");
  const auto restored = inverse.MapPoint(mapped);
  Require(std::abs(restored.x() - 1) < 0.00001 && std::abs(restored.y() - 2) < 0.00001, "inverse point mapping");
  gfx::Transform singular;
  singular.Scale(0, 1);
  Require(!singular.GetInverse(&inverse), "singular transform rejection");

  gfx::Rect rectangle(-7, 13, 101, 37);
  auto bytes = gfx::mojom::Rect::Serialize(&rectangle);
  gfx::Rect output;
  Require(gfx::mojom::Rect::Deserialize(bytes, &output) && output == rectangle, "original geometry wire roundtrip");
  Require(bytes.size() > 1, "geometry wire payload");
  bytes.pop_back();
  Require(!gfx::mojom::Rect::Deserialize(bytes, &output), "truncated geometry wire rejection");
  gfx::Range range(9, 3);
  Require(range.is_reversed() && range.Intersect(gfx::Range(6, 12)) == gfx::Range(6, 9), "native reversed range intersection");
  auto range_bytes = gfx::mojom::Range::Serialize(&range);
  gfx::Range decoded;
  Require(gfx::mojom::Range::Deserialize(range_bytes, &decoded) && decoded == range && decoded.is_reversed(), "original reversed range wire roundtrip");
}

void CheckCodecAndBuffers() {
  constexpr std::array<uint8_t, 16> pixels = {1, 2, 3, 255, 4, 5, 6, 127, 0, 0, 0, 0, 200, 177, 31, 255};
  auto encoded = gfx::PNGCodec::Encode(pixels.data(), gfx::PNGCodec::FORMAT_RGBA, gfx::Size(2, 2), 8, false, {});
  Require(encoded && !encoded->empty(), "gfx PNG encoding");
  auto decoded = gfx::PNGCodec::Decode(*encoded, gfx::PNGCodec::FORMAT_RGBA);
  Require(decoded && decoded->width == 2 && decoded->height == 2 && decoded->output.size() == pixels.size() && std::memcmp(decoded->output.data(), pixels.data(), pixels.size()) == 0, "gfx PNG RGBA alpha roundtrip");
  (*encoded)[0] ^= 1;
  Require(!gfx::PNGCodec::Decode(*encoded, gfx::PNGCodec::FORMAT_RGBA), "invalid gfx PNG rejection");
  size_t bytes;
  Require(gfx::NumberOfPlanesForLinearBufferFormat(gfx::BufferFormat::YUV_420_BIPLANAR) == 2 && gfx::BufferSizeForBufferFormatChecked(gfx::Size(4, 4), gfx::BufferFormat::YUV_420_BIPLANAR, &bytes) && bytes == 24 && gfx::BufferOffsetForBufferFormat(gfx::Size(4, 4), gfx::BufferFormat::YUV_420_BIPLANAR, 1) == 16, "native NV12 plane layout");
  Require(!gfx::RowSizeForBufferFormatChecked(std::numeric_limits<size_t>::max(), gfx::BufferFormat::RGBA_8888, 0, &bytes), "buffer row overflow rejection");
  char* format = drmGetFormatName(DRM_FORMAT_ARGB8888);
  Require(format && std::strcmp(format, "AR24") == 0, "native DRM format name");
  std::free(format);
  char* modifier = drmGetFormatModifierName(DRM_FORMAT_MOD_LINEAR);
  Require(modifier && std::strcmp(modifier, "LINEAR") == 0, "generated DRM modifier table");
  std::free(modifier);
}

void CheckDataPack() {
  base::ScopedTempDir directory;
  Require(directory.CreateUniqueTempDir(), "resource pack scratch directory");
  const auto first = directory.GetPath().AppendASCII("first.pak");
  const auto second = directory.GetPath().AppendASCII("second.pak");
  const std::string_view binary("left\0right", 10);
  const std::map<uint16_t, std::string_view> resources = {{1, binary}, {2, binary}, {40000, "tail"}};
  Require(ui::DataPack::WritePack(first, resources, ui::DataPack::BINARY) && ui::DataPack::WritePack(second, resources, ui::DataPack::BINARY), "original resource pack writing");
  std::string one, two;
  Require(base::ReadFileToString(first, &one) && base::ReadFileToString(second, &two) && one == two, "resource pack path independent bytes");
  ui::DataPack pack(ui::kScaleFactorNone);
  Require(pack.LoadFromPath(first) && pack.GetTextEncodingType() == ui::DataPack::BINARY, "native resource pack loading");
  Require(pack.GetStringView(1) == binary && pack.GetStringView(2) == binary && pack.GetStringView(40000) == "tail" && !pack.HasResource(42), "binary resource and duplicate value lookup");
  one.resize(3);
  ui::DataPack invalid(ui::kScaleFactorNone);
  Require(!invalid.LoadFromBuffer(base::as_byte_span(one)), "truncated resource pack rejection");
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 2, "declared ICU argument");
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  Require(base::FeatureList::InitInstance("", ""), "default feature initialization");
  base::SingleThreadTaskExecutor executor;
  base::File data(base::MakeAbsoluteFilePath(base::FilePath(argv[1])), base::File::FLAG_OPEN | base::File::FLAG_READ);
  Require(data.IsValid() && base::i18n::InitializeICUWithFileDescriptor(data.TakePlatformFile(), base::MemoryMappedFile::Region::kWholeFile), "declared ICU initialization");
  base::Thread thread("gfx-mojo-io");
  base::Thread::Options options;
  options.message_pump_type = base::MessagePumpType::IO;
  Require(thread.StartWithOptions(std::move(options)), "native Mojo IO thread");
  mojo::core::Configuration configuration;
  configuration.is_broker_process = true;
  mojo::core::Init(configuration);
  mojo::core::ScopedIPCSupport support(thread.task_runner(), mojo::core::ScopedIPCSupport::ShutdownPolicy::CLEAN);
  CheckGeometry();
  CheckCodecAndBuffers();
  CheckDataPack();
}

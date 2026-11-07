// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <utility>
#include <vector>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/files/memory_mapped_file.h"
#include "base/i18n/icu_util.h"
#include "base/task/single_thread_task_executor.h"
#include "base/threading/thread.h"
#include "mojo/core/embedder/embedder.h"
#include "mojo/core/embedder/scoped_ipc_support.h"
#include "ui/display/display.h"
#include "ui/display/display_list.h"
#include "ui/display/display_observer.h"
#include "ui/display/mojom/display.mojom.h"
#include "ui/display/mojom/screen_infos.mojom.h"
#include "ui/display/screen_infos.h"
#include "ui/gfx/geometry/insets.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: display %s\n", message);
    std::exit(1);
  }
}

void CheckDisplayModel() {
  display::Display monitor(17, gfx::Rect(0, 0, 1920, 1080));
  monitor.UpdateWorkAreaFromInsets(gfx::Insets::TLBR(24, 0, 36, 0));
  monitor.SetScaleAndBounds(2, gfx::Rect(-1920, 200, 1920, 1080));
  Require(monitor.bounds() == gfx::Rect(-960, 100, 960, 540) && monitor.GetSizeInPixel() == gfx::Size(1920, 1080) && monitor.native_origin() == gfx::Point(-1920, 200), "scaled native and logical display coordinates");
  Require(monitor.work_area() == gfx::Rect(-960, 124, 960, 480) && monitor.GetLocalWorkArea() == gfx::Rect(0, 24, 960, 480), "work area insets survive scale and relocation");
  monitor.SetRotationAsDegree(270);
  monitor.set_panel_rotation(display::Display::ROTATE_90);
  monitor.set_touch_support(display::Display::TouchSupport::AVAILABLE);
  monitor.set_label("Public display fixture");
  monitor.set_display_frequency(144);
  auto bytes = display::mojom::Display::Serialize(&monitor);
  display::Display decoded;
  Require(display::mojom::Display::Deserialize(bytes, &decoded) && decoded.id() == monitor.id() && decoded.bounds() == monitor.bounds() && decoded.work_area() == monitor.work_area() && decoded.GetSizeInPixel() == monitor.GetSizeInPixel() && decoded.native_origin() == monitor.native_origin() && decoded.device_scale_factor() == 2 && decoded.rotation() == display::Display::ROTATE_270 && decoded.touch_support() == monitor.touch_support() && decoded.label() == monitor.label() && decoded.display_frequency() == 144, "original display wire roundtrip");
  bytes.resize(bytes.size() - 1);
  Require(!display::mojom::Display::Deserialize(bytes, &decoded), "truncated display wire rejection");
}

class DisplayEvents : public display::DisplayObserver {
 public:
  void OnDisplayAdded(const display::Display& monitor) override { added.push_back(monitor.id()); }
  void OnDisplaysRemoved(const display::Displays& monitors) override {
    for (const auto& monitor : monitors) removed.push_back(monitor.id());
  }
  void OnDisplayMetricsChanged(const display::Display& monitor, uint32_t metrics) override {
    changed_id = monitor.id();
    changed_metrics = metrics;
  }
  std::vector<int64_t> added;
  std::vector<int64_t> removed;
  int64_t changed_id = -1;
  uint32_t changed_metrics = 0;
};

void CheckDisplayList() {
  DisplayEvents events;
  display::DisplayList list;
  list.AddObserver(&events);
  display::Display left(17, gfx::Rect(-960, 0, 960, 540));
  display::Display right(29, gfx::Rect(0, 0, 1920, 1080));
  list.AddDisplay(left, display::DisplayList::Type::PRIMARY);
  list.AddDisplay(right, display::DisplayList::Type::NOT_PRIMARY);
  Require(list.IsValid() && list.displays().size() == 2 && list.GetPrimaryDisplayIterator()->id() == 17 && events.added == std::vector<int64_t>({17, 29}), "native display enumeration and observer additions");
  right.SetRotationAsDegree(90);
  const auto changed = list.UpdateDisplay(right);
  Require((changed & display::DisplayObserver::DISPLAY_METRIC_ROTATION) && events.changed_id == 29 && events.changed_metrics == changed && list.FindDisplayById(29)->rotation() == display::Display::ROTATE_90, "native display rotation update notification");
  list.UpdateDisplay(right, display::DisplayList::Type::PRIMARY);
  Require(list.GetPrimaryDisplayIterator()->id() == 29, "native primary display transition");
  list.RemoveDisplay(17);
  Require(list.IsValid() && list.displays().size() == 1 && list.FindDisplayById(17) == list.displays().end() && events.removed == std::vector<int64_t>({17}), "native display removal notification");
  list.RemoveObserver(&events);
}

void CheckWireTypes() {
  display::ScreenInfo primary;
  primary.display_id = 17;
  primary.rect = gfx::Rect(0, 0, 960, 540);
  primary.available_rect = gfx::Rect(0, 24, 960, 516);
  primary.device_scale_factor = 2;
  display::ScreenInfo secondary;
  secondary.display_id = 29;
  secondary.rect = gfx::Rect(-1920, 0, 1920, 1080);
  display::ScreenInfos input;
  input.screen_infos = {primary, secondary};
  input.current_display_id = 29;
  auto bytes = display::mojom::ScreenInfos::Serialize(&input);
  display::ScreenInfos output;
  Require(display::mojom::ScreenInfos::Deserialize(bytes, &output) && output == input, "native multi-screen wire roundtrip");
  auto invalid = display::mojom::ScreenInfos::New();
  bytes = display::mojom::ScreenInfos::Serialize(&invalid);
  Require(!display::mojom::ScreenInfos::Deserialize(bytes, &output), "empty screen list wire rejection");
  invalid->screen_infos = {primary, primary};
  invalid->current_display_id = primary.display_id;
  bytes = display::mojom::ScreenInfos::Serialize(&invalid);
  Require(!display::mojom::ScreenInfos::Deserialize(bytes, &output), "duplicate screen identifier wire rejection");
  invalid->screen_infos = {primary, secondary};
  invalid->current_display_id = 99;
  bytes = display::mojom::ScreenInfos::Serialize(&invalid);
  Require(!display::mojom::ScreenInfos::Deserialize(bytes, &output), "absent selected screen wire rejection");
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
  base::Thread thread("display-mojo-io");
  base::Thread::Options options;
  options.message_pump_type = base::MessagePumpType::IO;
  Require(thread.StartWithOptions(std::move(options)), "native Mojo IO thread");
  mojo::core::Configuration configuration;
  configuration.is_broker_process = true;
  mojo::core::Init(configuration);
  mojo::core::ScopedIPCSupport support(thread.task_runner(), mojo::core::ScopedIPCSupport::ShutdownPolicy::CLEAN);
  CheckDisplayModel();
  CheckDisplayList();
  CheckWireTypes();
}

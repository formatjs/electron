// SPDX-License-Identifier: MIT
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/files/memory_mapped_file.h"
#include "base/i18n/icu_util.h"
#include "base/memory/ref_counted.h"
#include "base/task/single_thread_task_executor.h"
#include "base/time/time.h"
#include "third_party/snappy/src/snappy.h"
#include "ui/events/event.h"
#include "ui/events/keycodes/dom/dom_code.h"
#include "ui/events/keycodes/dom/dom_key.h"
#include "ui/events/keycodes/dom/keycode_converter.h"
#include "ui/events/keycodes/keyboard_codes.h"
#include "ui/gfx/geometry/point_f.h"
#include "ui/gfx/geometry/vector2d.h"
#include "ui/gfx/geometry/transform.h"
#include "ui/gfx/x/xproto.h"
#include "ui/gfx/x/xproto_internal.h"
#include <xcb/xcb.h>
#include <xkbcommon/xkbcommon.h>

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: events %s\n", message);
    std::exit(1);
  }
}

void CheckInputEvents() {
  const auto when = base::TimeTicks() + base::Milliseconds(7);
  ui::KeyEvent key(ui::EventType::kKeyPressed, ui::VKEY_A, ui::DomCode::US_A,
                   ui::EF_CONTROL_DOWN, ui::DomKey::FromCharacter('a'), when);
  Require(key.GetCharacter() == 1 && key.GetCodeString() == "KeyA", "native control character and physical key conversion");
  auto clone = key.Clone();
  key.SetFlags(ui::EF_SHIFT_DOWN);
  Require(clone->AsKeyEvent()->GetCharacter() == 1 && clone->IsControlDown() && !clone->IsShiftDown(), "key clone preserves independent modifier state");
  Require(ui::KeycodeConverter::CodeStringToDomCode("IntlBackslash") == ui::DomCode::INTL_BACKSLASH && ui::KeycodeConverter::DomCodeToCodeString(ui::DomCode::INTL_BACKSLASH) == "IntlBackslash" && ui::KeycodeConverter::CodeStringToDomCode("NoSuchPhysicalKey") == ui::DomCode::NONE, "native ISO physical key mapping and invalid key rejection");
  ui::MouseWheelEvent wheel(gfx::Vector2d(12, -120), gfx::PointF(8, 10), gfx::PointF(8, 10), when, ui::EF_SHIFT_DOWN, 0);
  gfx::Transform inverse;
  inverse.Scale(0.5f, 0.5f);
  wheel.UpdateForRootTransform(inverse, gfx::Transform());
  auto wheel_clone = wheel.Clone();
  Require(wheel.location_f() == gfx::PointF(4, 5) && wheel.root_location_f() == gfx::PointF(4, 5) && wheel_clone->AsMouseWheelEvent()->x_offset() == wheel.x_offset() && wheel_clone->AsMouseWheelEvent()->y_offset() == wheel.y_offset() && wheel_clone->time_stamp() == when, "native wheel transform and clone semantics");
}

void CheckDeclaredKeyboardLayout() {
  auto* context = xkb_context_new(static_cast<xkb_context_flags>(XKB_CONTEXT_NO_DEFAULT_INCLUDES | XKB_CONTEXT_NO_ENVIRONMENT_NAMES));
  Require(context != nullptr, "native keyboard context without host includes");
  constexpr char layout[] = R"XKB(xkb_keymap {
    xkb_keycodes "fixture" { minimum=8; maximum=255; <AC01>=38; <LFSH>=50; };
    xkb_types "fixture" { type "TWO_LEVEL" { modifiers=Shift; map[Shift]=Level2; level_name[Level1]="Base"; level_name[Level2]="Shift"; }; };
    xkb_compatibility "fixture" { interpret Shift_L { action=SetMods(modifiers=Shift); }; };
    xkb_symbols "fixture" { key <AC01> { type="TWO_LEVEL", [a,A] }; key <LFSH> { [Shift_L] }; modifier_map Shift { <LFSH> }; };
  };)XKB";
  auto* keymap = xkb_keymap_new_from_string(context, layout, XKB_KEYMAP_FORMAT_TEXT_V1, XKB_KEYMAP_COMPILE_NO_FLAGS);
  Require(keymap != nullptr, "native parser compiles explicit keyboard layout");
  auto* state = xkb_state_new(keymap);
  Require(state && xkb_state_key_get_utf32(state, 38) == 'a', "native keyboard base state");
  xkb_state_update_key(state, 50, XKB_KEY_DOWN);
  Require(xkb_state_key_get_utf32(state, 38) == 'A', "native keyboard shift transition");
  xkb_state_update_key(state, 50, XKB_KEY_UP);
  Require(xkb_state_key_get_utf32(state, 38) == 'a', "native keyboard shift release");
  Require(!xkb_keymap_new_from_string(context, "invalid keymap", XKB_KEYMAP_FORMAT_TEXT_V1, XKB_KEYMAP_COMPILE_NO_FLAGS), "invalid keyboard layout rejection");
  xkb_state_unref(state);
  xkb_keymap_unref(keymap);
  xkb_context_unref(context);
}

template <class T>
void Store(std::array<uint8_t, 32>& packet, size_t offset, T value) {
  std::memcpy(packet.data() + offset, &value, sizeof(value));
}

void CheckProtocolAndCompression() {
  std::array<uint8_t, 32> packet{};
  packet[0] = 2;
  packet[1] = 38;
  Store<uint16_t>(packet, 2, 0x1234);
  Store<uint32_t>(packet, 4, 123456);
  Store<uint32_t>(packet, 12, 0x321);
  Store<int16_t>(packet, 20, -11);
  Store<int16_t>(packet, 24, -7);
  Store<uint16_t>(packet, 28, 1);
  packet[30] = 1;
  x11::ReadBuffer buffer(base::MakeRefCounted<x11::UnretainedRefCountedMemory>(packet.data()));
  x11::KeyEvent event;
  x11::ReadEvent<x11::KeyEvent>(&event, &buffer);
  Require(static_cast<uint8_t>(event.detail) == 38 && event.sequence == 0x1234 && static_cast<uint32_t>(event.time) == 123456 && static_cast<uint32_t>(event.event) == 0x321 && event.root_x == -11 && event.event_x == -7 && static_cast<uint16_t>(event.state) == 1 && event.same_screen == 1 && buffer.offset == 32, "original X11 keyboard wire decoding");
  char* host = nullptr;
  int display, screen;
  Require(xcb_parse_display("fixture:12.3", &host, &display, &screen) && std::strcmp(host, "fixture") == 0 && display == 12 && screen == 3, "native XCB display string parsing");
  std::free(host);
  Require(!xcb_parse_display("fixture:invalid", nullptr, nullptr, nullptr), "invalid XCB display rejection");
  std::string input;
  for (int i = 0; i < 256; ++i) input.append("wire\0payload", 12);
  std::string compressed, decoded;
  snappy::Compress(input.data(), input.size(), &compressed);
  Require(compressed.size() < input.size() / 2 && snappy::Uncompress(compressed.data(), compressed.size(), &decoded) && decoded == input, "native Snappy binary roundtrip");
  compressed.resize(1);
  Require(!snappy::Uncompress(compressed.data(), compressed.size(), &decoded), "truncated Snappy stream rejection");
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
  CheckInputEvents();
  CheckDeclaredKeyboardLayout();
  CheckProtocolAndCompression();
}

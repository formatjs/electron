// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#include <string>
#include <string_view>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "base/files/file.h"
#include "base/files/file_path.h"
#include "base/files/memory_mapped_file.h"
#include "base/i18n/icu_util.h"
#include "base/no_destructor.h"
#include "third_party/blink/public/platform/platform.h"
#include "third_party/blink/public/platform/web_string.h"
#include "third_party/blink/renderer/platform/graphics/color.h"
#include "third_party/blink/renderer/platform/language.h"
#include "third_party/blink/renderer/platform/text/character.h"
#include "third_party/blink/renderer/platform/text/character_break_iterator.h"
#include "third_party/blink/renderer/platform/wtf/allocator/partitions.h"
#include "third_party/blink/renderer/platform/wtf/text/atomic_string.h"
#include "third_party/blink/renderer/platform/wtf/text/wtf_string.h"
#include "third_party/blink/renderer/platform/wtf/wtf.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: blink_platform %s\n", message);
    std::exit(1);
  }
}

void Stage(const char* stage) {
  std::fprintf(stderr, "blink_platform probe stage: %s\n", stage);
}

class ProbePlatform final : public blink::Platform {
 public:
  blink::WebString DefaultLocale() override {
    return blink::WebString::FromUTF8("en-US");
  }
};
}  // namespace

int main(int argc, char** argv) {
  Stage("entry");
  Require(argc == 2, "declared ICU data available");
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  Require(base::FeatureList::InitInstance("", ""), "native feature list initializes");
  base::File data(base::FilePath(argv[1]),
                  base::File::FLAG_OPEN | base::File::FLAG_READ);
  Require(data.IsValid(), "pinned ICU data opens");
  Require(base::i18n::InitializeICUWithFileDescriptor(
              data.TakePlatformFile(), base::MemoryMappedFile::Region::kWholeFile),
          "source ICU initializes with declared data");
  Stage("icu");
  static base::NoDestructor<ProbePlatform> platform;
  blink::Platform::SetCurrentPlatformForTesting(platform.get());
  blink::Partitions::Initialize();
  blink::InitializeWtf();
  blink::InitializePlatformLanguage();
  Stage("platform");

  const std::string utf8 = "Qe\u0301\U0001F469\u200D\U0001F4BB\U0001F1EF\U0001F1F5!";
  const blink::String text = blink::String::FromUTF8(utf8);
  Require(text.length() == 13 && text.Utf8() == utf8,
          "UTF8 round trip preserves supplementary characters");
  Require(blink::String::FromUTF8(std::string_view("\xed\xa0\x80", 3)).IsNull(),
          "UTF8 surrogate encoding is rejected");
  Require(blink::NumGraphemeClusters(text) == 5,
          "combining sequence emoji and flag form grapheme clusters");
  blink::CharacterBreakIterator clusters(text);
  for (int boundary : {1, 3, 8, 12, 13})
    Require(clusters.Next() == boundary, "grapheme boundaries match UTF16 offsets");
  Require(clusters.Next() == blink::kTextBreakDone && !clusters.IsBreak(5),
          "emoji joiner stays inside a single grapheme");
  const blink::AtomicString interned(text);
  const blink::AtomicString same(blink::String::FromUTF8(utf8));
  Require(interned.Impl() == same.Impl(), "native string interning shares storage");
  Require(blink::Character::IsCJKIdeographOrSymbol(0x4e00) &&
              !blink::Character::IsCJKIdeographOrSymbol('Q') &&
              blink::Character::IsEmoji(0x1f469) &&
              !blink::Character::IsEmoji('Q'),
          "generated Unicode properties distinguish ideographs and emoji");
  const auto* navy = blink::FindColor("navy");
  Require(navy && navy->argb_value == 0xff000080u,
          "native gperf color lookup returns CSS navy");
  blink::Color tomato;
  Require(tomato.SetNamedColor(blink::String("ToMaTo")) &&
              tomato.Rgb() == 0xffff6347u &&
              !tomato.SetNamedColor(blink::String("invalid-css-color")),
          "CSS named colors fold case and reject unknown names");
  Stage("done");
}

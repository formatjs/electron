// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <string>

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
#include "third_party/blink/renderer/modules/websockets/websocket_common.h"
#include "third_party/blink/renderer/platform/language.h"
#include "third_party/blink/renderer/platform/wtf/vector.h"
#include "third_party/blink/renderer/platform/wtf/allocator/partitions.h"
#include "third_party/blink/renderer/platform/wtf/text/wtf_string.h"
#include "third_party/blink/renderer/platform/wtf/wtf.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: blink_modules %s\n", message);
    std::exit(1);
  }
}

void Stage(const char* stage) {
  std::fprintf(stderr, "blink_modules probe stage: %s\n", stage);
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

  using Common = blink::WebSocketCommon;
  Require(Common::IsValidSubprotocolString(blink::String("chat.v2")),
          "WebSocket token accepts dots");
  Require(Common::IsValidSubprotocolString(blink::String("chat-v2_!#$%&'*+^`|~")),
          "WebSocket token accepts permitted punctuation");
  for (const char* invalid : {"", "chat room", "chat/room", "chat,room", "chat:room"}) {
    Require(!Common::IsValidSubprotocolString(blink::String(invalid)),
            "WebSocket token rejects empty strings and separators");
  }
  Require(!Common::IsValidSubprotocolString(blink::String::FromUTF8("caf\xC3\xA9")),
          "WebSocket token rejects non-ASCII code points");
  Require(Common::EncodeSubprotocolString(blink::String::FromUTF8("caf\xC3\xA9")).Utf8() ==
              "caf\\u00E9",
          "WebSocket error text escapes Unicode");
  Require(Common::EncodeSubprotocolString(blink::String("a\\b\n")).Utf8() ==
              "a\\\\b\\u000A",
          "WebSocket error text escapes backslashes and controls");
  blink::Vector<blink::String> protocols;
  protocols.push_back(blink::String("chat"));
  protocols.push_back(blink::String("superchat"));
  Require(Common::JoinStrings(protocols, ", ").Utf8() == "chat, superchat",
          "WebSocket protocol header joins in order");
  Require(Common::JoinStrings(blink::Vector<blink::String>(), ", ").empty(),
          "WebSocket empty protocol list stays empty");
  Stage("done");
}

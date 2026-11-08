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
#include "third_party/blink/renderer/core/html/parser/html_input_stream.h"
#include "third_party/blink/renderer/core/html/parser/html_parser_options.h"
#include "third_party/blink/renderer/core/html/parser/html_tokenizer.h"
#include "third_party/blink/renderer/platform/language.h"
#include "third_party/blink/renderer/platform/wtf/allocator/partitions.h"
#include "third_party/blink/renderer/platform/wtf/text/wtf_string.h"
#include "third_party/blink/renderer/platform/wtf/wtf.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: blink_core %s\n", message);
    std::exit(1);
  }
}

void Stage(const char* stage) {
  std::fprintf(stderr, "blink_core probe stage: %s\n", stage);
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

  blink::HTMLParserOptions options;
  blink::HTMLTokenizer tokenizer(options);
  blink::HTMLInputStream input;
  input.AppendToEnd(blink::SegmentedString(blink::String::FromUTF8(
      "<DIV data-x='a&amp;b'>A&amp;&#x1f642;\r\n</DIV><!--ok-->")));
  input.MarkEndOfFile();
  auto* token = tokenizer.NextToken(input.Current());
  Require(token && token->GetType() == blink::HTMLToken::kStartTag &&
              token->GetName().AsString().Utf8() == "div",
          "HTML tag names fold ASCII case");
  Require(token->Attributes().size() == 1 &&
              token->Attributes()[0].GetName().Utf8() == "data-x" &&
              token->Attributes()[0].Value().Utf8() == "a&b",
          "quoted attribute entities decode");
  std::string text;
  tokenizer.ClearToken();
  while ((token = tokenizer.NextToken(input.Current())) &&
         token->GetType() == blink::HTMLToken::kCharacter) {
    text += token->Characters().AsString().Utf8();
    tokenizer.ClearToken();
  }
  Require(text == "A&\U0001F642\n", "numeric entities and CRLF normalize");
  Require(token && token->GetType() == blink::HTMLToken::kEndTag &&
              token->GetName().AsString().Utf8() == "div",
          "HTML end tag parses");
  tokenizer.ClearToken();
  token = tokenizer.NextToken(input.Current());
  Require(token && token->GetType() == blink::HTMLToken::kComment &&
              token->Data().AsString().Utf8() == "ok",
          "HTML comment parses");
  tokenizer.ClearToken();
  token = tokenizer.NextToken(input.Current());
  Require(token && token->GetType() == blink::HTMLToken::kEndOfFile,
          "closed stream emits EOF");

  blink::HTMLTokenizer incremental(options);
  blink::SegmentedString first(blink::String("<script "));
  Require(!incremental.NextToken(first), "incomplete tag waits for input");
  blink::SegmentedString rest(blink::String("type='javascript'>"));
  token = incremental.NextToken(rest);
  Require(token && token->GetType() == blink::HTMLToken::kStartTag &&
              token->GetName().AsString().Utf8() == "script" &&
              token->Attributes().size() == 1 &&
              token->Attributes()[0].Value().Utf8() == "javascript",
          "split attribute continues without losing tokenizer state");
  Stage("done");
}

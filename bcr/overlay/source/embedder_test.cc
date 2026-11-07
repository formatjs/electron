// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <string>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "base/files/file.h"
#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/files/memory_mapped_file.h"
#include "base/i18n/break_iterator.h"
#include "base/i18n/case_conversion.h"
#include "base/i18n/encoding_detection.h"
#include "base/i18n/icu_string_conversions.h"
#include "base/i18n/icu_util.h"
#include "base/task/single_thread_task_executor.h"
#include "base/task/thread_pool/thread_pool_instance.h"
#include "gin/array_buffer.h"
#include "gin/dictionary.h"
#include "gin/object_template_builder.h"
#include "gin/public/context_holder.h"
#include "gin/public/isolate_holder.h"
#include "gin/v8_initializer.h"
#include "tools/v8_context_snapshot/buildflags.h"
#include "v8.h"

#if !BUILDFLAG(USE_V8_CONTEXT_SNAPSHOT) || !defined(V8_ENABLE_SANDBOX)
#error Preserve captured context snapshot and sandbox configuration.
#endif

namespace {
void Stage(const char* name) {
  std::fprintf(stderr, "embedder probe stage: %s\n", name);
}

void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: embedder %s\n", message);
    std::exit(1);
  }
}

void CheckI18n() {
  Require(base::i18n::FoldCase(u"Stra\u00dfe") == u"strasse", "Unicode full case folding");
  std::u16string decoded;
  Require(base::CodepageToUTF16("caf\xe9", "windows-1252", base::OnStringConversionError::FAIL, &decoded) && decoded == u"caf\u00e9", "legacy encoding conversion");
  Require(!base::CodepageToUTF16("\xc3(", "UTF-8", base::OnStringConversionError::FAIL, &decoded), "malformed UTF-8 rejected");
  base::i18n::BreakIterator words(u"hello world", base::i18n::BreakIterator::BREAK_WORD);
  Require(words.Init(), "word iterator initialization");
  int count = 0;
  while (words.Advance()) if (words.IsWord()) ++count;
  Require(count == 2, "ICU word boundaries");
  base::i18n::BreakIterator graphemes(u"e\u0301\U0001f469\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466", base::i18n::BreakIterator::BREAK_CHARACTER);
  Require(graphemes.Init(), "grapheme iterator initialization");
  count = 0;
  while (graphemes.Advance()) ++count;
  Require(count == 2, "combining mark and emoji grapheme boundaries");
  std::string encoding;
  const std::string text = "caf\xc3\xa9 \xe4\xb8\x96\xe7\x95\x8c \xd9\x85\xd8\xb1\xd8\xad\xd8\xa8\xd8\xa7 ";
  std::string sample;
  for (int i = 0; i < 64; ++i) sample += text;
  Require(base::DetectEncoding(sample, &encoding) && encoding == "UTF-8", "native CED UTF-8 detection");
}

int calls = 0;
int Add(int lhs, int rhs) { ++calls; return lhs + rhs; }

v8::Local<v8::Value> Run(v8::Isolate* isolate, v8::Local<v8::Context> context, const char* source) {
  auto text = v8::String::NewFromUtf8(isolate, source).ToLocalChecked();
  return v8::Script::Compile(context, text).ToLocalChecked()->Run(context).ToLocalChecked();
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 3, "declared ICU and snapshot arguments");
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  Require(base::FeatureList::InitInstance("", ""), "default feature initialization");
  base::SingleThreadTaskExecutor executor;
  base::ThreadPoolInstance::CreateAndStartWithDefaultParams("EmbedderProbe");
  Stage("i18n");
  const auto icu_path = base::MakeAbsoluteFilePath(base::FilePath(argv[1]));
  const auto snapshot_path = base::MakeAbsoluteFilePath(base::FilePath(argv[2]));
  Require(!icu_path.empty() && !snapshot_path.empty(), "declared runtime paths");
  base::File data(icu_path, base::File::FLAG_OPEN | base::File::FLAG_READ);
  Require(data.IsValid(), "declared ICU file");
  Require(base::i18n::InitializeICUWithFileDescriptor(data.TakePlatformFile(), base::MemoryMappedFile::Region::kWholeFile), "ICU descriptor initialization");
  CheckI18n();
  Stage("snapshot");
  gin::V8Initializer::LoadV8SnapshotFromFile(
      base::File(snapshot_path, base::File::FLAG_OPEN | base::File::FLAG_READ),
      nullptr, gin::V8SnapshotFileType::kDefault);
  v8::StartupData snapshot;
  gin::V8Initializer::GetV8ExternalSnapshotData(&snapshot);
  Require(snapshot.data && snapshot.raw_size > 0, "Gin mapped generated snapshot");
  Stage("gin");
  gin::IsolateHolder::Initialize(gin::IsolateHolder::kNonStrictMode, gin::ArrayBufferAllocator::SharedInstance());
  {
    gin::IsolateHolder holder(executor.task_runner(), gin::IsolateHolder::IsolateType::kTest);
    auto* isolate = holder.isolate();
    v8::Isolate::Scope isolate_scope(isolate);
    v8::HandleScope handles(isolate);
    gin::ContextHolder context_holder(isolate);
    auto context = v8::Context::New(isolate);
    context_holder.SetContext(context);
    v8::Context::Scope context_scope(context);
    auto object = gin::ObjectTemplateBuilder(isolate).SetMethod("add", &Add).Build()->NewInstance(context).ToLocalChecked();
    gin::Dictionary bridge(isolate, object);
    Require(bridge.Set("label", std::string("native-\xcf\x80")), "C++ to JS string conversion");
    std::string label;
    Require(bridge.Get("label", &label) && label == "native-\xcf\x80", "JS to C++ string conversion");
    Require(context->Global()->Set(context, v8::String::NewFromUtf8Literal(isolate, "bridge"), object).FromMaybe(false), "native binding installation");
    Stage("callback");
    Require(Run(isolate, context, "bridge.add(19, 23)")->Int32Value(context).FromMaybe(0) == 42 && calls == 1, "JS calls native Gin method");
    {
      v8::TryCatch caught(isolate);
      auto script = v8::Script::Compile(context, v8::String::NewFromUtf8Literal(isolate, "bridge.add('bad', 1)")).ToLocalChecked();
      Require(script->Run(context).IsEmpty() && caught.HasCaught() && calls == 1, "Gin rejects invalid native argument");
    }
    auto buffer = v8::ArrayBuffer::New(isolate, 16);
    gin::ArrayBuffer converted;
    Require(gin::ConvertFromV8(isolate, buffer, &converted) && converted.num_bytes() == 16, "sandboxed Gin array buffer");
    Stage("gc");
    isolate->LowMemoryNotification();
    Require(Run(isolate, context, "bridge.add(20, 22)")->Int32Value(context).FromMaybe(0) == 42 && calls == 2, "Gin binding survives collection");
  }
  Stage("shutdown");
  base::ThreadPoolInstance::Get()->Shutdown();
  v8::V8::Dispose();
  v8::V8::DisposePlatform();
  base::i18n::ResetGlobalsForTesting();
  Stage("done");
  return 0;
}

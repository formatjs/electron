// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <string_view>

#include "libplatform/libplatform.h"
#include "v8-inspector.h"
#include "v8.h"

#if !defined(V8_COMPRESS_POINTERS) || !defined(V8_ENABLE_SANDBOX) || !defined(V8_INTL_SUPPORT) || !defined(V8_USE_PERFETTO)
#error Preserve captured pointer compression, sandbox, Intl and tracing profile.
#endif

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: V8 engine %s\n", message);
    std::exit(1);
  }
}

v8::Local<v8::String> Text(v8::Isolate* isolate, const char* value) {
  return v8::String::NewFromUtf8(isolate, value).ToLocalChecked();
}

v8_inspector::StringView View(std::string_view value) {
  return v8_inspector::StringView(reinterpret_cast<const uint8_t*>(value.data()), value.size());
}

class Client final : public v8_inspector::V8InspectorClient {
 public:
  Client(v8::Isolate* isolate, v8::Local<v8::Context> context) : isolate_(isolate), context_(isolate, context) {}
  v8::Local<v8::Context> ensureDefaultContextInGroup(int group) override {
    return group == 1 ? context_.Get(isolate_) : v8::Local<v8::Context>();
  }
 private:
  v8::Isolate* isolate_;
  v8::Global<v8::Context> context_;
};

class Channel final : public v8_inspector::V8Inspector::Channel {
 public:
  void sendResponse(int id, std::unique_ptr<v8_inspector::StringBuffer> value) override { responses[id] = std::move(value); }
  void sendNotification(std::unique_ptr<v8_inspector::StringBuffer>) override {}
  void flushProtocolNotifications() override {}
  std::map<int, std::unique_ptr<v8_inspector::StringBuffer>> responses;
};

void CheckInspector(v8::Isolate* isolate, v8::Local<v8::Context> context) {
  Client client(isolate, context);
  Channel channel;
  auto inspector = v8_inspector::V8Inspector::create(isolate, &client);
  inspector->contextCreated(v8_inspector::V8ContextInfo(context, 1, View("source")));
  auto session = inspector->connectShared(1, &channel, v8_inspector::StringView(), v8_inspector::V8Inspector::kFullyTrusted,
                                           v8_inspector::V8Inspector::kNotWaitingForDebugger);
  session->dispatchProtocolMessage(View(R"({"id":1,"method":"Runtime.enable"})"));
  session->dispatchProtocolMessage(View(R"({"id":2,"method":"Runtime.evaluate","params":{"expression":"globalThis.inspectorProbe = 6 * 7","returnByValue":true}})"));
  Require(channel.responses.count(1) && channel.responses.count(2), "inspector responses");
  const auto response = channel.responses[2]->string();
  const auto json = response.is8Bit()
      ? v8::String::NewFromOneByte(isolate, response.characters8(), v8::NewStringType::kNormal, response.length()).ToLocalChecked()
      : v8::String::NewFromTwoByte(isolate, response.characters16(), v8::NewStringType::kNormal, response.length()).ToLocalChecked();
  auto parsed = v8::JSON::Parse(context, json).ToLocalChecked().As<v8::Object>();
  auto result = parsed->Get(context, Text(isolate, "result")).ToLocalChecked().As<v8::Object>();
  auto remote = result->Get(context, Text(isolate, "result")).ToLocalChecked().As<v8::Object>();
  Require(remote->Get(context, Text(isolate, "value")).ToLocalChecked()->Int32Value(context).FromMaybe(0) == 42, "inspector evaluation");
  session.reset();
  inspector->contextDestroyed(context);
}

void CheckJavaScript(v8::Isolate* isolate, v8::Local<v8::Context> context) {
  const char* program = R"JS((() => {
    const bytes = new Uint8Array([0,97,115,109,1,0,0,0,1,7,1,96,2,127,127,1,127,3,2,1,0,7,7,1,3,97,100,100,0,0,10,9,1,7,0,32,0,32,1,106,11]);
    const wasm = new WebAssembly.Instance(new WebAssembly.Module(bytes));
    if (wasm.exports.add(20, 22) !== 42) throw new Error('Wasm add');
    if ('e\u0301'.normalize('NFC') !== '\u00e9') throw new Error('normalization');
    if (new Intl.Collator('de', {sensitivity: 'base'}).compare('stra\u00dfe', 'strasse') !== 0) throw new Error('collation');
    const before = Temporal.ZonedDateTime.from('2024-03-10T01:30-05:00[America/New_York]');
    const after = before.add({hours: 1});
    if (after.hour !== 3 || after.minute !== 30 || after.offset !== '-04:00') throw new Error('Temporal DST');
    let rejected = false;
    try { Temporal.PlainDate.from({year: 2023, month: 2, day: 29}, {overflow: 'reject'}); } catch (error) { rejected = error instanceof RangeError; }
    if (!rejected) throw new Error('Temporal rejection');
    if (Array.from({length: 4096}, (_, index) => index).reduce((sum, item) => sum + item, 0) !== 8386560) throw new Error('JS execution');
    return true;
  })())JS";
  v8::TryCatch caught(isolate);
  v8::Local<v8::Script> script;
  v8::Local<v8::Value> value;
  const bool success = v8::Script::Compile(context, Text(isolate, program)).ToLocal(&script) && script->Run(context).ToLocal(&value);
  if (!success && caught.HasCaught()) {
    v8::String::Utf8Value message(isolate, caught.Exception());
    std::fprintf(stderr, "V8 engine script exception: %s\n", *message ? *message : "unknown");
  }
  Require(success && value->IsTrue(), "JavaScript Wasm Intl Temporal execution");
}

void CheckSyntaxError(v8::Isolate* isolate, v8::Local<v8::Context> context) {
  v8::TryCatch caught(isolate);
  Require(v8::Script::Compile(context, Text(isolate, "function (" )).IsEmpty() && caught.HasCaught(), "syntax error reporting");
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 3, "declared runtime data arguments");
  Require(v8::V8::InitializeICUDefaultLocation(argv[0], argv[1]), "declared ICU data");
  v8::V8::InitializeExternalStartupDataFromFile(argv[2]);
  v8::V8::SetFlagsFromString("--harmony-temporal");
  auto platform = v8::platform::NewDefaultPlatform();
  v8::V8::InitializePlatform(platform.get());
  Require(v8::V8::Initialize(), "initialization");
  std::unique_ptr<v8::ArrayBuffer::Allocator> allocator(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
  v8::Isolate::CreateParams parameters;
  parameters.array_buffer_allocator = allocator.get();
  auto* isolate = v8::Isolate::New(parameters);
  Require(isolate != nullptr, "isolate allocation");
  {
    v8::Isolate::Scope entered(isolate);
    v8::HandleScope handles(isolate);
    auto context = v8::Context::New(isolate);
    v8::Context::Scope current(context);
    CheckJavaScript(isolate, context);
    CheckInspector(isolate, context);
    CheckSyntaxError(isolate, context);
    isolate->LowMemoryNotification();
    Require(context->Global()->Get(context, Text(isolate, "inspectorProbe")).ToLocalChecked()->Int32Value(context).FromMaybe(0) == 42, "context survives collection");
  }
  isolate->Dispose();
  Require(v8::V8::Dispose(), "disposal");
  v8::V8::DisposePlatform();
  return 0;
}

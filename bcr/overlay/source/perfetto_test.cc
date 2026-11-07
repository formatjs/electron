// SPDX-License-Identifier: MIT
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <string>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#include "json/json.h"
#include "perfetto/tracing.h"
#include "perfetto/tracing/track_event.h"
#include "protos/perfetto/config/track_event/track_event_config.gen.h"
#include "protos/perfetto/trace/interned_data/interned_data.pbzero.h"
#include "protos/perfetto/trace/trace.pbzero.h"
#include "protos/perfetto/trace/trace_packet.pbzero.h"
#include "protos/perfetto/trace/track_event/debug_annotation.pbzero.h"
#include "protos/perfetto/trace/track_event/track_event.pbzero.h"

static_assert(JSON_USE_EXCEPTION == 0);
static_assert(JSON_USE_NULLREF == 0);
static_assert(PERFETTO_BUILDFLAG(PERFETTO_CHROMIUM_BUILD));
static_assert(PERFETTO_DCHECK_IS_ON());

PERFETTO_DEFINE_CATEGORIES(perfetto::Category("source"), perfetto::Category("excluded"));
PERFETTO_TRACK_EVENT_STATIC_STORAGE();

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: Perfetto %s\n", message);
    std::exit(1);
  }
}

void CheckJson() {
  Json::Value original(Json::objectValue);
  original["revision"] = 142;
  original["binary"] = std::string("a\0b", 3);
  Json::StreamWriterBuilder writer;
  const auto text = Json::writeString(writer, original);
  Json::Value restored;
  Json::CharReaderBuilder reader;
  std::string errors;
  Require(std::unique_ptr<Json::CharReader>(reader.newCharReader())->parse(text.data(), text.data() + text.size(), &restored, &errors) && restored == original,
          "JsonCpp roundtrip");
  const rlimit no_core = {0, 0};
  Require(setrlimit(RLIMIT_CORE, &no_core) == 0, "JsonCpp core limit");
  const pid_t child = fork();
  Require(child >= 0, "JsonCpp child process");
  if (child == 0) {
    Json::Value invalid("not an integer");
    invalid.asInt();
    _exit(99);
  }
  int status = 0;
  Require(waitpid(child, &status, 0) == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT,
          "JsonCpp invalid conversion aborts");
}

void CheckTrace() {
  perfetto::TracingInitArgs arguments;
  arguments.backends = perfetto::kInProcessBackend;
  perfetto::Tracing::Initialize(arguments);
  perfetto::TrackEvent::Register();
  perfetto::TraceConfig config;
  config.add_buffers()->set_size_kb(1024);
  auto* data_source = config.add_data_sources()->mutable_config();
  data_source->set_name("track_event");
  perfetto::protos::gen::TrackEventConfig categories;
  categories.add_disabled_categories("*");
  categories.add_enabled_categories("source");
  data_source->set_track_event_config_raw(categories.SerializeAsString());
  auto session = perfetto::Tracing::NewTrace();
  session->Setup(config);
  session->StartBlocking();
  {
    TRACE_EVENT("source", "SourceProbe", "iteration", 42);
    TRACE_EVENT("excluded", "HiddenProbe");
  }
  perfetto::TrackEvent::Flush();
  session->StopBlocking();
  const auto bytes = session->ReadTraceBlocking();
  session.reset();
  perfetto::Tracing::Shutdown();
  Require(!bytes.empty(), "trace bytes");
  std::map<std::pair<uint32_t, uint64_t>, std::string> names;
  bool found = false;
  perfetto::protos::pbzero::Trace::Decoder trace(reinterpret_cast<const uint8_t*>(bytes.data()), bytes.size());
  for (auto item = trace.packet(); item; ++item) {
    perfetto::protos::pbzero::TracePacket::Decoder packet(*item);
    const auto sequence = packet.trusted_packet_sequence_id();
    if (packet.has_interned_data()) {
      perfetto::protos::pbzero::InternedData::Decoder interned(packet.interned_data());
      for (auto entry = interned.event_names(); entry; ++entry) {
        perfetto::protos::pbzero::EventName::Decoder name(*entry);
        names[{sequence, name.iid()}] = name.name().ToStdString();
      }
    }
    if (!packet.has_track_event()) continue;
    perfetto::protos::pbzero::TrackEvent::Decoder event(packet.track_event());
    const auto name = event.has_name() ? event.name().ToStdString() : names[{sequence, event.name_iid()}];
    Require(name != "HiddenProbe", "disabled category filtered");
    if (name != "SourceProbe" || event.type() != perfetto::protos::pbzero::TrackEvent::TYPE_SLICE_BEGIN) continue;
    for (auto value = event.debug_annotations(); value; ++value) {
      perfetto::protos::pbzero::DebugAnnotation::Decoder annotation(*value);
      if (annotation.has_int_value() && annotation.int_value() == 42) found = true;
    }
  }
  Require(found, "decoded trace event and annotation");
}
}  // namespace

int main() {
  CheckJson();
  CheckTrace();
  return 0;
}

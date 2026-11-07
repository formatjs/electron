// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string>

#include "google/protobuf/dynamic_message.h"
#include "google/protobuf/unknown_field_set.h"
#include "protobuf_probe.pb.h"
#include "protobuf_lite_probe.pb.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: Protobuf %s\n", message);
    std::exit(1);
  }
}

void CheckFull() {
  electron_source_probe::Envelope original;
  original.set_name("source-built-\xc3\xa9");
  original.add_values(-9223372036854775807LL);
  original.add_values(0);
  original.add_values(9223372036854775807LL);
  (*original.mutable_blobs())["binary"] = std::string("a\0b\xff", 4);
  original.set_text("replaced");
  original.set_number(-17);
  original.set_note("");
  Require(!original.has_text() && original.has_number() && original.has_note(), "oneof and optional presence");
  std::string wire;
  Require(original.SerializeToString(&wire), "full serialization");
  wire.append("\x98\x06\x07", 3);
  electron_source_probe::Envelope parsed;
  Require(parsed.ParseFromString(wire) && parsed.name() == original.name() && parsed.values_size() == 3 &&
              parsed.values(0) == original.values(0) && parsed.values(2) == original.values(2) &&
              parsed.blobs().at("binary") == original.blobs().at("binary") && parsed.number() == -17 && parsed.has_note(),
          "full wire roundtrip");
  const auto& unknown = parsed.GetReflection()->GetUnknownFields(parsed);
  Require(unknown.field_count() == 1 && unknown.field(0).number() == 99 && unknown.field(0).varint() == 7, "unknown field preservation");
  google::protobuf::DynamicMessageFactory factory;
  std::unique_ptr<google::protobuf::Message> dynamic(factory.GetPrototype(parsed.GetDescriptor())->New());
  Require(dynamic->ParseFromString(wire), "dynamic message parsing");
  const auto* name = dynamic->GetDescriptor()->FindFieldByName("name");
  Require(name && dynamic->GetReflection()->GetString(*dynamic, name) == original.name(), "dynamic reflection");
  Require(!parsed.ParseFromString(std::string("\x0a\x05x", 3)), "truncated message rejected");
  Require(!parsed.ParseFromString(std::string("\x0a\x02\xc0\xaf", 4)), "invalid UTF8 rejected");
}

void CheckLite() {
  electron_source_probe::LiteEnvelope original;
  original.set_name("lite");
  original.add_values(-31);
  original.add_values(1234567890123LL);
  original.set_payload(std::string("\0\xff", 2));
  std::string wire;
  Require(original.SerializeToString(&wire), "lite serialization");
  wire.append("\x98\x06\x07", 3);
  electron_source_probe::LiteEnvelope parsed;
  Require(parsed.ParseFromString(wire) && parsed.name() == "lite" && parsed.values_size() == 2 &&
              parsed.values(0) == -31 && parsed.values(1) == 1234567890123LL && parsed.payload() == original.payload(),
          "lite wire roundtrip");
  Require(parsed.SerializeAsString().ends_with(std::string("\x98\x06\x07", 3)), "lite unknown field preservation");
  Require(!parsed.ParseFromString(std::string("\x12\x80", 2)), "malformed packed field rejected");
}
}  // namespace

int main() {
  CheckFull();
  CheckLite();
  return 0;
}

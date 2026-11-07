// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <string>

#include "base/at_exit.h"
#include "base/base64.h"
#include "base/functional/bind.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/location.h"
#include "base/message_loop/message_pump_type.h"
#include "base/run_loop.h"
#include "base/task/single_thread_task_executor.h"
#include "base/values.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: Chromium base %s\n", message);
    std::exit(1);
  }
}
}

int main() {
  base::AtExitManager at_exit;
  auto value = base::JSONReader::Read("{/*comment*/\"answer\":42,}",
      base::JSON_ALLOW_COMMENTS | base::JSON_ALLOW_TRAILING_COMMAS);
  Require(value && value->is_dict() && value->GetDict().FindInt("answer") == 42,
          "Rust JSON bridge parses Chromium extensions");
  Require(!base::JSONReader::Read("{\"answer\":42,}", base::JSON_PARSE_RFC),
          "strict JSON rejects trailing comma");
  Require(!base::JSONReader::Read("{\"answer\":}", base::JSON_PARSE_RFC),
          "malformed JSON rejected");
  std::string serialized;
  Require(base::JSONWriter::Write(*value, &serialized) && serialized == "{\"answer\":42}",
          "JSON serializes without extensions");
  std::string decoded;
  Require(base::Base64Decode(base::Base64Encode(serialized), &decoded) && decoded == serialized,
          "base64 round trip");
  base::SingleThreadTaskExecutor executor(base::MessagePumpType::UI);
  base::RunLoop loop;
  bool ran = false;
  executor.task_runner()->PostTask(FROM_HERE, base::BindOnce([&] {
    ran = true;
    loop.Quit();
  }));
  loop.Run();
  Require(ran, "native GLib message pump dispatches task");
  return 0;
}

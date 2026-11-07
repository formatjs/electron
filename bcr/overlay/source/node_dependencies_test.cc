// SPDX-License-Identifier: MIT
#include <arpa/inet.h>
#include <ada.h>
#include <ares.h>
#include <hdr/hdr_histogram.h>
#include <llhttp.h>
#include <nghttp2/nghttp2.h>
#include <simdjson.h>
#include <sqlite3.h>
#include <uvwasi.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

static void check(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "Node dependency check failed: %s\n", message);
    std::exit(1);
  }
}

static int body(llhttp_t* parser, const char*, size_t length) {
  *static_cast<size_t*>(parser->data) += length;
  return 0;
}

int main() {
  auto url = ada::parse<ada::url_aggregator>("https://example.com/a/../b?q=one two");
  check(bool(url) && url->get_href() == "https://example.com/b?q=one%20two", "URL normalization");
  check(!ada::parse<ada::url_aggregator>("https://[invalid]/"), "invalid URL rejection");

  check(ares_library_init(ARES_LIB_INIT_ALL) == ARES_SUCCESS, "c-ares initialization");
  unsigned char address[16] = {};
  const unsigned char expected[16] = {0x20, 0x01, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1};
  check(ares_inet_pton(AF_INET6, "2001:db8::1", address) == 1 && std::memcmp(address, expected, sizeof(expected)) == 0, "IPv6 conversion");
  check(ares_inet_pton(AF_INET6, "not-an-address", address) == 0, "invalid address rejection");
  ares_library_cleanup();

  hdr_histogram* histogram = nullptr;
  check(hdr_init(1, 1000000, 3, &histogram) == 0, "histogram initialization");
  check(hdr_record_value(histogram, 100) && hdr_record_value(histogram, 200), "histogram recording");
  check(histogram->total_count == 2 && hdr_value_at_percentile(histogram, 100) >= 200, "histogram percentile");
  hdr_close(histogram);

  llhttp_settings_t settings;
  llhttp_settings_init(&settings);
  settings.on_body = body;
  llhttp_t http;
  llhttp_init(&http, HTTP_REQUEST, &settings);
  size_t body_bytes = 0;
  http.data = &body_bytes;
  constexpr char request[] = "POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\n";
  check(llhttp_execute(&http, request, 17) == HPE_OK, "partial HTTP request");
  check(llhttp_execute(&http, request + 17, sizeof(request) - 1 - 17) == HPE_OK && body_bytes == 9, "chunked HTTP body");
  llhttp_init(&http, HTTP_REQUEST, &settings);
  constexpr char invalid[] = "BAD_METHOD / HTTP/1.1\r\n\r\n";
  check(llhttp_execute(&http, invalid, sizeof(invalid) - 1) != HPE_OK, "invalid HTTP method rejection");

  nghttp2_settings_entry entry = {NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS, 17};
  unsigned char payload[6] = {};
  check(nghttp2_pack_settings_payload2(payload, sizeof(payload), &entry, 1) == 6, "HTTP/2 settings encoding");
  check(payload[0] == 0 && payload[1] == 3 && payload[2] == 0 && payload[3] == 0 && payload[4] == 0 && payload[5] == 17, "HTTP/2 settings bytes");
  check(nghttp2_check_header_name(reinterpret_cast<const uint8_t*>("content-type"), 12) == 1, "HTTP/2 header acceptance");
  check(nghttp2_check_header_name(reinterpret_cast<const uint8_t*>("Invalid"), 7) == 0, "HTTP/2 uppercase header rejection");

  simdjson::dom::parser parser;
  simdjson::dom::element document;
  constexpr char json[] = "{\"answer\":42}";
  simdjson::padded_string padded(json, sizeof(json) - 1);
  check(!parser.parse(padded).get(document), "JSON parsing");
  uint64_t answer = 0;
  check(!document["answer"].get(answer) && answer == 42, "JSON integer lookup");

  sqlite3* database = nullptr;
  check(sqlite3_open(":memory:", &database) == SQLITE_OK, "SQLite initialization");
  check(sqlite3_compileoption_used("ENABLE_SESSION") == 1, "captured SQLite session feature");
  check(sqlite3_exec(database, "CREATE VIRTUAL TABLE messages USING fts5(body); INSERT INTO messages VALUES('native node source');", nullptr, nullptr, nullptr) == SQLITE_OK, "SQLite FTS5 creation and insert");
  sqlite3_stmt* statement = nullptr;
  check(sqlite3_prepare_v2(database, "SELECT body FROM messages WHERE messages MATCH 'native'", -1, &statement, nullptr) == SQLITE_OK, "SQLite query preparation");
  check(sqlite3_step(statement) == SQLITE_ROW && std::strcmp(reinterpret_cast<const char*>(sqlite3_column_text(statement, 0)), "native node source") == 0, "SQLite FTS5 query");
  sqlite3_finalize(statement);
  sqlite3_close(database);

  uvwasi_options_t options;
  uvwasi_options_init(&options);
  const char* arguments[] = {"node-dependencies", "payload"};
  options.argc = 2;
  options.argv = arguments;
  uvwasi_t wasi;
  check(uvwasi_init(&wasi, &options) == UVWASI_ESUCCESS, "WASI initialization");
  uvwasi_size_t count = 0, bytes = 0;
  check(uvwasi_args_sizes_get(&wasi, &count, &bytes) == UVWASI_ESUCCESS && count == 2, "WASI argument sizes");
  std::vector<char> buffer(bytes);
  std::vector<char*> values(count);
  check(uvwasi_args_get(&wasi, values.data(), buffer.data()) == UVWASI_ESUCCESS && std::strcmp(values[1], "payload") == 0, "WASI argument transfer");
  uvwasi_destroy(&wasi);

  std::puts("NODE_DEPENDENCIES_OK libraries=8");
}

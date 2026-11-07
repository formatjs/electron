// SPDX-License-Identifier: MIT
#include <arpa/inet.h>
#include <ada.h>
#include <ares.h>
#include <hdr/hdr_histogram.h>
#include <llhttp.h>
#include <nbytes.h>
#include <ncrypto.h>
#include <nghttp2/nghttp2.h>
#include <postject-api.h>
#include <simdjson.h>
#include <sqlite3.h>
#include <uvwasi.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

extern "C" const unsigned char node_dependency_note[];

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

  const char original[8] = {0, 1, 2, 3, 4, 5, 6, 7};
  struct SwapCase {
    bool (*swap)(char*, size_t);
    char expected[8];
  };
  const SwapCase swaps[] = {
      {nbytes::SwapBytes16, {1, 0, 3, 2, 5, 4, 7, 6}},
      {nbytes::SwapBytes32, {3, 2, 1, 0, 7, 6, 5, 4}},
      {nbytes::SwapBytes64, {7, 6, 5, 4, 3, 2, 1, 0}},
  };
  for (const auto& test : swaps) {
    alignas(8) char buffer[10] = {};
    buffer[0] = 0x5a;
    buffer[9] = 0x5b;
    std::memcpy(buffer + 1, original, sizeof(original));
    check(test.swap(buffer + 1, sizeof(original)) && std::memcmp(buffer + 1, test.expected, sizeof(original)) == 0, "unaligned byte swap");
    check(!test.swap(buffer + 1, 7) && std::memcmp(buffer + 1, test.expected, sizeof(original)) == 0, "invalid byte count rejected without mutation");
    check(buffer[0] == 0x5a && buffer[9] == 0x5b, "byte swap bounds");
  }

  // RFC 5869 A.1: https://www.rfc-editor.org/rfc/rfc5869.html#appendix-A.1
  unsigned char key[22], salt[13], info[10];
  std::memset(key, 0x0b, sizeof(key));
  for (size_t i = 0; i < sizeof(salt); ++i) salt[i] = i;
  for (size_t i = 0; i < sizeof(info); ++i) info[i] = 0xf0 + i;
  const unsigned char hkdf_expected[] = {
      0x3c, 0xb2, 0x5f, 0x25, 0xfa, 0xac, 0xd5, 0x7a, 0x90, 0x43, 0x4f, 0x64, 0xd0, 0x36,
      0x2f, 0x2a, 0x2d, 0x2d, 0x0a, 0x90, 0xcf, 0x1a, 0x5a, 0x4c, 0x5d, 0xb0, 0x2d, 0x56,
      0xec, 0xc4, 0xc5, 0xbf, 0x34, 0x00, 0x72, 0x08, 0xd5, 0xb8, 0x87, 0x18, 0x58, 0x65};
  const auto* sha256 = ncrypto::getDigestByName("sha256");
  check(sha256 != nullptr, "Node crypto SHA-256 lookup");
  auto derived = ncrypto::hkdf(sha256, {key, sizeof(key)}, {info, sizeof(info)}, {salt, sizeof(salt)}, sizeof(hkdf_expected));
  check(bool(derived) && derived.size() == sizeof(hkdf_expected) && std::memcmp(derived.get(), hkdf_expected, sizeof(hkdf_expected)) == 0, "Node crypto HKDF vector");
  check(ncrypto::checkHkdfLength(sha256, 255 * 32) && !ncrypto::checkHkdfLength(sha256, 255 * 32 + 1), "HKDF length boundary");
  check(!ncrypto::hkdf(sha256, {key, sizeof(key)}, {info, sizeof(info)}, {salt, sizeof(salt)}, 255 * 32 + 1), "oversized HKDF rejected");

  // Keep the declared note live under linker GC.
  check(node_dependency_note[0] == sizeof("electron-node-fixture"), "ELF note retained");
  check(!postject_has_resource(), "default Postject fuse remains disabled");
  size_t resource_size = 999;
  check(postject_find_resource("missing-resource", &resource_size, nullptr) == nullptr && resource_size == 0, "missing embedded resource");
  constexpr char resource[] = "declared resource bytes";
  const void* embedded = postject_find_resource("electron-node-fixture", &resource_size, nullptr);
  check(embedded != nullptr && resource_size == sizeof(resource) - 1 && std::memcmp(embedded, resource, resource_size) == 0, "embedded ELF resource bytes");
  postject_options options_override;
  postject_options_init(&options_override);
  options_override.elf_section_name = "electron-node-fixture";
  check(postject_find_resource("ignored-resource", &resource_size, &options_override) == embedded, "ELF resource name override");

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

  std::puts("NODE_DEPENDENCIES_OK libraries=11");
}

// SPDX-License-Identifier: MIT
#include <array>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "blapi.h"
#include "secport.h"

namespace {
void Require(bool value) {
  if (!value) {
    std::fputs("NSS integrity generation failed\n", stderr);
    std::exit(1);
  }
}
std::vector<unsigned char> Read(const char* path) {
  std::ifstream file(path, std::ios::binary);
  Require(file.is_open());
  std::vector<unsigned char> bytes{std::istreambuf_iterator<char>(file), {}};
  Require(!file.bad());
  return bytes;
}
uint32_t Integer(const unsigned char* data) {
  return (uint32_t(data[0]) << 24) | (uint32_t(data[1]) << 16) |
         (uint32_t(data[2]) << 8) | data[3];
}
void WriteInteger(FILE* file, uint32_t value) {
  unsigned char bytes[] = {static_cast<unsigned char>(value >> 24),
                           static_cast<unsigned char>(value >> 16),
                           static_cast<unsigned char>(value >> 8),
                           static_cast<unsigned char>(value)};
  Require(std::fwrite(bytes, 1, sizeof(bytes), file) == sizeof(bytes));
}
void WriteItem(FILE* file, const SECItem& item) {
  WriteInteger(file, item.len);
  Require(std::fwrite(item.data, 1, item.len, file) == item.len);
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 5);
  auto parameters = Read(argv[1]);
  auto seeds = Read(argv[2]);
  auto module = Read(argv[3]);
  Require(seeds.size() == 64 && !module.empty());
  size_t offset = 0;
  std::array<SECItem, 3> items;
  for (auto& item : items) {
    Require(parameters.size() - offset >= 4);
    const auto length = Integer(parameters.data() + offset);
    offset += 4;
    Require(length > 0 && length <= parameters.size() - offset);
    item = {siBuffer, parameters.data() + offset, length};
    offset += length;
  }
  Require(offset == parameters.size());
  PQGParams params{nullptr, items[0], items[1], items[2]};
  Require(BL_Init() == SECSuccess && RNG_RNGInit() == SECSuccess);
  DSAPrivateKey* key = nullptr;
  Require(DSA_NewKeyFromSeed(&params, seeds.data(), &key) == SECSuccess);
  unsigned char digest_bytes[32], signature_bytes[64];
  Require(SHA256_HashBuf(digest_bytes, module.data(), module.size()) == SECSuccess);
  SECItem digest{siBuffer, digest_bytes, sizeof(digest_bytes)};
  SECItem signature{siBuffer, signature_bytes, sizeof(signature_bytes)};
  Require(DSA_SignDigestWithSeed(key, &signature, &digest, seeds.data() + 32) == SECSuccess);
  Require(signature.len == sizeof(signature_bytes));
  DSAPublicKey public_key{key->params, key->publicValue};
  Require(DSA_VerifyDigest(&public_key, &signature, &digest) == SECSuccess);
  FILE* output = std::fopen(argv[4], "wb");
  Require(output != nullptr);
  const unsigned char header[] = {0xf1, 0xc5, 1, 2};
  Require(std::fwrite(header, 1, sizeof(header), output) == sizeof(header));
  WriteInteger(output, 12);
  WriteInteger(output, 1);  // CKK_DSA.
  for (const auto& item : items) WriteItem(output, item);
  WriteItem(output, key->publicValue);
  WriteItem(output, signature);
  Require(std::fclose(output) == 0);
  PORT_FreeArena(key->params.arena, PR_TRUE);
  RNG_RNGShutdown();
  BL_Cleanup();
}

// SPDX-License-Identifier: MIT
#include <openssl/evp.h>
#include <openssl/ssl.h>

#include <cstring>

int main() {
  const EVP_MD* digest = EVP_get_digestbyname("ripemd160");
  if (!digest) return 1;
  const unsigned char expected[] = {
      0x8e, 0xb2, 0x08, 0xf7, 0xe0, 0x5d, 0x98, 0x7a, 0x9b, 0x04,
      0x4a, 0x8e, 0x98, 0xc6, 0xb0, 0x87, 0xf1, 0x5a, 0x0b, 0xfc};
  unsigned char result[EVP_MAX_MD_SIZE];
  unsigned length = 0;
  if (!EVP_Digest("abc", 3, result, &length, digest, nullptr) ||
      length != sizeof(expected) || std::memcmp(result, expected, length)) return 2;
  for (const char* name : {"aes-128-cfb", "aes-256-cfb", "bf-cbc", "bf-cfb",
                           "bf-ecb", "des-ede3", "rc2-40-cbc"}) {
    if (!EVP_get_cipherbyname(name)) return 3;
  }
  const unsigned char key[16] = {};
  const unsigned char iv[16] = {};
  const unsigned char plaintext[] = "Electron Node crypto";
  unsigned char ciphertext[64], decrypted[64];
  int first = 0, last = 0, decoded = 0, tail = 0;
  bssl::UniquePtr<EVP_CIPHER_CTX> context(EVP_CIPHER_CTX_new());
  const EVP_CIPHER* cipher = EVP_get_cipherbyname("aes-128-cfb");
  if (!context || !EVP_EncryptInit_ex(context.get(), cipher, nullptr, key, iv) ||
      !EVP_EncryptUpdate(context.get(), ciphertext, &first, plaintext, sizeof(plaintext) - 1) ||
      !EVP_EncryptFinal_ex(context.get(), ciphertext + first, &last) ||
      !EVP_DecryptInit_ex(context.get(), cipher, nullptr, key, iv) ||
      !EVP_DecryptUpdate(context.get(), decrypted, &decoded, ciphertext, first + last) ||
      !EVP_DecryptFinal_ex(context.get(), decrypted + decoded, &tail) ||
      decoded + tail != sizeof(plaintext) - 1 ||
      std::memcmp(decrypted, plaintext, sizeof(plaintext) - 1)) return 4;
  bssl::UniquePtr<SSL_CTX> tls_context(SSL_CTX_new(TLS_method()));
  bssl::UniquePtr<SSL> tls(tls_context ? SSL_new(tls_context.get()) : nullptr);
  return tls ? 0 : 5;
}

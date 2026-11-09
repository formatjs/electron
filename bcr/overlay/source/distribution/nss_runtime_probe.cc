// SPDX-License-Identifier: MIT
#include <dlfcn.h>
#include <string>

#include "lib/freebl/loader.h"

int main(int argc, char** argv) {
  if (argc != 2) return 1;
  const std::string root = argv[1];
  // FREEBL_NO_DEPEND resolves stubs from already-loaded NSS/NSPR libraries.
  void* nss = dlopen((root + "/libnss3.so").c_str(), RTLD_NOW | RTLD_LOCAL);
  if (!nss) return 6;
  void* freebl = dlopen((root + "/libfreeblpriv3.so").c_str(), RTLD_NOW | RTLD_LOCAL);
  if (!freebl) return 2;
  auto get_vector = reinterpret_cast<FREEBLGetVectorFn*>(dlsym(freebl, "FREEBL_GetVector"));
  if (!get_vector) return 3;
  const auto* vector = get_vector();
  if (!vector) return 4;
  for (const char* name : {"freebl3", "freeblpriv3", "nssdbm3", "softokn3"}) {
    if (!vector->p_BLAPI_SHVerifyFile((root + "/lib" + name + ".so").c_str())) return 5;
  }
  auto initialize = reinterpret_cast<int (*)(const char*)>(dlsym(nss, "NSS_NoDB_Init"));
  auto random = reinterpret_cast<int (*)(unsigned char*, int)>(dlsym(nss, "PK11_GenerateRandom"));
  auto shutdown = reinterpret_cast<int (*)()>(dlsym(nss, "NSS_Shutdown"));
  unsigned char bytes[32];
  if (!initialize || !random || !shutdown || initialize(nullptr) != 0 ||
      random(bytes, sizeof(bytes)) != 0 || shutdown() != 0) return 7;
  return dlclose(freebl) == 0 && dlclose(nss) == 0 ? 0 : 8;
}

#include <dlfcn.h>

int main(void) {
  void *library = dlopen("libfixture_answer.so", RTLD_NOW | RTLD_LOCAL);
  if (!library) return 1;
  int (*answer)(void) = (int (*)(void))dlsym(library, "fixture_answer");
  int result = !answer || answer() != 42;
  dlclose(library);
  return result;
}

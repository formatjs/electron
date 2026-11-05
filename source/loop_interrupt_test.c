// SPDX-License-Identifier: MIT
#include <stdio.h>
#include <uv.h>

int main(void) {
  uv_loop_t loop;
  int result = uv_loop_init(&loop);
  if (result != 0) return 1;
  result = uv_loop_configure(&loop, UV_LOOP_INTERRUPT_ON_IO_CHANGE);
  if (result != 0) {
    fprintf(stderr, "Electron loop interrupt unavailable: %s\n", uv_strerror(result));
    return 1;
  }
  return uv_loop_close(&loop) != 0;
}

// SPDX-License-Identifier: MIT
#include <node_api.h>

NAPI_MODULE_INIT() {
  napi_value answer;
  if (napi_create_int32(env, 42, &answer) != napi_ok ||
      napi_set_named_property(env, exports, "answer", answer) != napi_ok) {
    return nullptr;
  }
  return exports;
}

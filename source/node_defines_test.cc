// SPDX-License-Identifier: MIT
#include <string_view>

#define TRACE_EVENT0 "outer"
#include "electron/push_and_undef_node_defines.h"
#ifdef TRACE_EVENT0
#error "Node trace macro was not isolated"
#endif
#define TRACE_EVENT0 "inner"
#include "electron/pop_node_defines.h"
static_assert(std::string_view(TRACE_EVENT0) == "outer");

int main() { return 0; }

// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <string>

#include "builtins-generated/bytecodes-builtins-list.h"
#include "src/interpreter/bytecodes.h"

namespace v8::internal {
namespace {
using interpreter::Bytecode;
using interpreter::BytecodeOperands;
using interpreter::Bytecodes;
using interpreter::OperandScale;

void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: %s\n", message);
    std::exit(1);
  }
}

struct Handler {
  OperandScale scale;
  Bytecode bytecode;
  const char* name;
};

#define ENTRY(Name, Scale, Code) {Scale, Code, #Name},
#define IF_TSA(TSA_MACRO, CSA_MACRO, ...) CSA_MACRO(__VA_ARGS__)
constexpr Handler kHandlers[] = {BUILTIN_LIST_BYTECODE_HANDLERS(ENTRY, ENTRY)};
#undef IF_TSA
#undef ENTRY

void CheckDispatchTables() {
  bool seen[BytecodeOperands::kOperandScaleCount][Bytecodes::kBytecodeCount] = {};
  int counts[BytecodeOperands::kOperandScaleCount] = {};
  for (const auto& handler : kHandlers) {
    const int scale = BytecodeOperands::OperandScaleAsIndex(handler.scale);
    const int code = static_cast<int>(handler.bytecode);
    Require(!seen[scale][code], "bytecode handler unique");
    seen[scale][code] = true;
    ++counts[scale];
    std::string name = Bytecodes::ToString(handler.bytecode, handler.scale, "");
    if (handler.bytecode == Bytecode::kStar0) name = "ShortStar";
    Require(name + "Handler" == handler.name, "bytecode handler name");
  }

  for (const auto scale : {OperandScale::kSingle, OperandScale::kDouble,
                           OperandScale::kQuadruple}) {
    for (int code = 0; code < Bytecodes::kBytecodeCount; ++code) {
      Require(seen[BytecodeOperands::OperandScaleAsIndex(scale)][code] ==
                  Bytecodes::BytecodeHasHandler(static_cast<Bytecode>(code), scale),
              "bytecode handler coverage");
    }
  }
  Require(counts[0] == kNumberOfBytecodeHandlers &&
              counts[1] == kNumberOfWideBytecodeHandlers && counts[2] == counts[1],
          "bytecode handler counts");

  for (int code = 0; code < Bytecodes::kBytecodeCount; ++code) {
    const auto bytecode = static_cast<Bytecode>(code);
    const int mapped = kWideBytecodeToBuiltinsMapping[code];
    if (!Bytecodes::BytecodeHasHandler(bytecode, OperandScale::kDouble)) {
      Require(mapped == kIllegalBytecodeHandlerEncoding, "bytecode illegal wide encoding");
      continue;
    }
    Require(mapped < kNumberOfWideBytecodeHandlers, "bytecode dense index bounds");
    const auto& wide = kHandlers[kNumberOfBytecodeHandlers + mapped];
    const auto& extra = kHandlers[kNumberOfBytecodeHandlers + kNumberOfWideBytecodeHandlers + mapped];
    Require(wide.bytecode == bytecode && wide.scale == OperandScale::kDouble &&
                extra.bytecode == bytecode && extra.scale == OperandScale::kQuadruple,
            "bytecode wide dispatch mapping");
  }
}

std::string Read(const char* path) {
  std::ifstream file(path, std::ios::binary);
  Require(file.good(), "bytecode generated file readable");
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
}  // namespace
}  // namespace v8::internal

int main(int argc, char** argv) {
  using namespace v8::internal;
  Require(argc == 3, "bytecode generated file arguments");
  const auto first = Read(argv[1]);
  Require(!first.empty() && first == Read(argv[2]), "bytecode generation path reproducibility");
  CheckDispatchTables();
  return 0;
}

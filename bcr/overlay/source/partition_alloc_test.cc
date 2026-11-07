// SPDX-License-Identifier: MIT
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <limits>
#include <unistd.h>

#include "partition_alloc/partition_address_space.h"
#include "partition_alloc/shim/allocator_shim.h"

namespace {
void Checkpoint(const char* text) {
  const ssize_t written = write(STDERR_FILENO, text, std::strlen(text));
  (void)written;
}

void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: %s\n", message);
    std::exit(1);
  }
}

void Managed(void* memory) {
  Require(memory && partition_alloc::IsManagedByPartitionAlloc(reinterpret_cast<uintptr_t>(memory)), "PartitionAlloc heap ownership");
}

void Pattern(void* memory, size_t length, unsigned char value) {
  for (size_t index = 0; index < length; ++index) {
    Require(static_cast<unsigned char*>(memory)[index] == value, "PartitionAlloc preserved bytes");
  }
}
}  // namespace

int main() {
  Checkpoint("PARTITION_ALLOC_ENTRY\n");
  void* memory = allocator_shim::UncheckedAlloc(3333);
  Managed(memory);
  std::memset(memory, 0x6b, 3333);
  Checkpoint("PARTITION_ALLOC_ALLOC\n");
  void* grown = allocator_shim::UncheckedRealloc(memory, 6553);
  Managed(grown);
  Pattern(grown, 3333, 0x6b);
  Require(!allocator_shim::UncheckedRealloc(grown, std::numeric_limits<size_t>::max()), "PartitionAlloc failed realloc returns null");
  Pattern(grown, 3333, 0x6b);
  allocator_shim::UncheckedFree(grown);
  Checkpoint("PARTITION_ALLOC_REALLOC\n");

  memory = allocator_shim::UncheckedCalloc(37, 29);
  Managed(memory);
  Pattern(memory, 37 * 29, 0);
  allocator_shim::UncheckedFree(memory);
  Require(!allocator_shim::UncheckedCalloc(std::numeric_limits<size_t>::max(), 2), "PartitionAlloc calloc overflow rejected");
  Require(!allocator_shim::UncheckedAlloc(std::numeric_limits<size_t>::max()), "PartitionAlloc oversized allocation rejected");
  Checkpoint("PARTITION_ALLOC_CALLOC\n");

  for (size_t alignment : {size_t{16}, size_t{64}, size_t{4096}}) {
    // The implementation takes size, alignment.
    memory = allocator_shim::UncheckedAlignedAlloc(3333, alignment);
    Managed(memory);
    Require(reinterpret_cast<uintptr_t>(memory) % alignment == 0, "PartitionAlloc requested alignment");
    std::memset(memory, 0x7c, 3333);
    grown = allocator_shim::UncheckedAlignedRealloc(memory, 6553, alignment);
    Managed(grown);
    Require(reinterpret_cast<uintptr_t>(grown) % alignment == 0, "PartitionAlloc realloc alignment");
    Pattern(grown, 3333, 0x7c);
    allocator_shim::UncheckedAlignedFree(grown);
  }
  Checkpoint("PARTITION_ALLOC_ALIGNED\n");

  memory = std::malloc(128);
  Managed(memory);
  std::free(memory);
  Checkpoint("PARTITION_ALLOC_LIBC\n");
  auto* value = new uint64_t(0x123456789abcdef0ULL);
  Managed(value);
  Require(*value == 0x123456789abcdef0ULL, "PartitionAlloc C++ new value");
  delete value;
  Checkpoint("PARTITION_ALLOC_NEW\n");
  allocator_shim::UncheckedFree(nullptr);
  Checkpoint("PARTITION_ALLOC_DONE\n");
  return 0;
}

// SPDX-License-Identifier: MIT
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <utility>
#include <vector>

#include "partition_alloc/partition_address_space.h"
#include "src/objects/js-temporal-zoneinfo64.h"
#include "temporal_rs/AnyCalendarKind.hpp"
#include "temporal_rs/ArithmeticOverflow.hpp"
#include "temporal_rs/Disambiguation.hpp"
#include "temporal_rs/Duration.hpp"
#include "temporal_rs/OffsetDisambiguation.hpp"
#include "temporal_rs/PlainDate.hpp"
#include "temporal_rs/TimeZone.hpp"
#include "temporal_rs/ZonedDateTime.hpp"
#include "unicode/uclean.h"
#include "unicode/udata.h"

extern "C" unsigned char* electron_rust_allocate_pattern();
extern "C" void electron_rust_free_pattern(unsigned char*);
extern "C" bool electron_rust_fallible_reserve();

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: %s\n", message);
    std::exit(1);
  }
}

template <typename T, typename E>
T Take(temporal_rs::diplomat::result<T, E> value, const char* message) {
  Require(value.is_ok(), message);
  return std::move(value).ok().value();
}

void CheckAllocator() {
  auto* bytes = electron_rust_allocate_pattern();
  Require(bytes && partition_alloc::IsManagedByPartitionAlloc(reinterpret_cast<uintptr_t>(bytes)), "Temporal Rust heap ownership");
  for (int index = 0; index < 256; ++index) Require(bytes[index] == 0x6b, "Temporal Rust buffer bytes");
  electron_rust_free_pattern(bytes);
  Require(electron_rust_fallible_reserve(), "Temporal Rust unchecked allocation failure");
}

void CheckCalendar() {
  using namespace temporal_rs;
  auto leap = Take(PlainDate::try_new(2024, 2, 29, AnyCalendarKind::Iso), "Temporal leap date construction");
  Require(leap->year() == 2024 && leap->month() == 2 && leap->day() == 29 && leap->in_leap_year() && leap->days_in_month() == 29, "Temporal leap date fields");
  Require(partition_alloc::IsManagedByPartitionAlloc(reinterpret_cast<uintptr_t>(leap.get())), "Temporal object heap ownership");
  Require(!PlainDate::try_new_with_overflow(2023, 2, 29, AnyCalendarKind::Iso, ArithmeticOverflow::Reject).is_ok(), "Temporal invalid leap date rejected");
  auto constrained = Take(PlainDate::try_new_constrain(2023, 2, 31, AnyCalendarKind::Iso), "Temporal constrained date construction");
  Require(constrained->day() == 28 && constrained->month() == 2, "Temporal constrained date fields");
  auto one_day = Take(Duration::from_utf8("P1D"), "Temporal duration parsing");
  auto next = Take(leap->add(*one_day, ArithmeticOverflow::Reject), "Temporal calendar addition");
  Require(next->year() == 2024 && next->month() == 3 && next->day() == 1, "Temporal calendar rollover");
  auto japanese = leap->with_calendar(AnyCalendarKind::Japanese);
  Require(japanese->era() == "reiwa" && japanese->era_year().value_or(0) == 6, "Temporal Japanese calendar data");
}

void CheckTimezone() {
  using namespace temporal_rs;
  auto& provider = v8::internal::ZoneInfo64Provider::Singleton().Provider();
  Require(!TimeZone::try_from_identifier_str_with_provider("Etc/DefinitelyMissing", provider).is_ok(), "Temporal unknown timezone rejected");
  auto before = Take(ZonedDateTime::from_utf8_with_provider("2024-03-10T01:30-05:00[America/New_York]", Disambiguation::Reject, OffsetDisambiguation::Reject, provider), "Temporal timezone parsing");
  auto hour = Take(Duration::from_utf8("PT1H"), "Temporal hour duration parsing");
  auto after = Take(before->add_with_provider(*hour, ArithmeticOverflow::Reject, provider), "Temporal DST addition");
  Require(before->hour() == 1 && before->offset_nanoseconds() == -18000000000000LL && after->hour() == 3 && after->minute() == 30 && after->offset_nanoseconds() == -14400000000000LL, "Temporal DST transition");
  Require(!ZonedDateTime::from_utf8_with_provider("2024-03-10T02:30[America/New_York]", Disambiguation::Reject, OffsetDisambiguation::Reject, provider).is_ok(), "Temporal DST gap rejected");
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 2, "Temporal declared ICU data argument");
  std::ifstream input(argv[1], std::ios::binary | std::ios::ate);
  Require(input.good(), "Temporal declared ICU data readable");
  const auto bytes = input.tellg();
  Require(bytes > 0 && bytes <= 64 * 1024 * 1024, "Temporal declared ICU data size");
  std::vector<std::max_align_t> data((static_cast<size_t>(bytes) + sizeof(std::max_align_t) - 1) / sizeof(std::max_align_t));
  input.seekg(0);
  Require(static_cast<bool>(input.read(reinterpret_cast<char*>(data.data()), bytes)), "Temporal declared ICU data complete");
  UErrorCode status = U_ZERO_ERROR;
  udata_setFileAccess(UDATA_NO_FILES, &status);
  udata_setCommonData(data.data(), &status);
  u_init(&status);
  Require(U_SUCCESS(status), "Temporal declared ICU data initialized");
  CheckAllocator();
  CheckCalendar();
  CheckTimezone();
  return 0;
}

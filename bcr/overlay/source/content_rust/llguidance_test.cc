// SPDX-License-Identifier: MIT
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>

#include "third_party/rust/chromium_crates_io/vendor/llguidance-v1/llguidance.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: llguidance %s\n", message);
    std::exit(1);
  }
}
}  // namespace

int main() {
  std::array<uint8_t, 128> bytes;
  std::array<uint32_t, 129> lengths{};
  for (uint32_t index = 0; index < bytes.size(); ++index) {
    bytes[index] = static_cast<uint8_t>(index);
    lengths[index] = 1;
  }
  const char* slices[] = {nullptr};
  LlgTokenizerInit config{};
  config.vocab_size = static_cast<uint32_t>(lengths.size());
  config.tok_eos = 128;
  config.token_lens = lengths.data();
  config.token_bytes = bytes.data();
  config.use_approximate_greedy_tokenize_fn = true;
  config.slices = slices;
  char error[512]{};
  std::unique_ptr<LlgTokenizer, decltype(&llg_free_tokenizer)> tokenizer(
      llg_new_tokenizer(&config, error, sizeof(error)), llg_free_tokenizer);
  Require(tokenizer != nullptr, "ASCII tokenizer initializes through C ABI");
  LlgConstraintInit init{};
  llg_constraint_init_set_defaults(&init, tokenizer.get());
  Require(llg_validate_grammar(&init, "regex", "[a-z]+", error, sizeof(error)) >= 0,
          "valid regex compiles");
  Require(llg_validate_grammar(&init, "regex", "[", error, sizeof(error)) == -1,
          "invalid regex is rejected");
  std::unique_ptr<LlgMatcher, decltype(&llg_free_matcher)> matcher(
      llg_new_matcher(&init, "regex", "ab[0-9]"), llg_free_matcher);
  Require(matcher && !llg_matcher_is_error(matcher.get()), "matcher initializes");
  Require(llg_matcher_compute_mask(matcher.get()) == 0, "token mask computes");
  const auto* mask = llg_matcher_get_mask(matcher.get());
  Require(mask && (mask['a' / 32] & (uint32_t{1} << ('a' % 32))) &&
              !(mask['z' / 32] & (uint32_t{1} << ('z' % 32))),
          "mask allows grammar prefix and excludes other tokens");
  Require(llg_matcher_consume_token(matcher.get(), 'a') == 0 &&
              llg_matcher_consume_token(matcher.get(), 'b') == 0,
          "valid prefix advances matcher");
  Require(!llg_matcher_is_accepting(matcher.get()), "incomplete prefix cannot finish");
  Require(llg_matcher_consume_token(matcher.get(), '7') == 0 &&
              llg_matcher_is_accepting(matcher.get()),
          "complete grammar accepts matching tokens");
  Require(llg_matcher_reset(matcher.get()) == 0 &&
              !llg_matcher_is_accepting(matcher.get()),
          "reset restores initial grammar state");
  Require(llg_matcher_consume_token(matcher.get(), 'z') == -1 &&
              llg_matcher_is_error(matcher.get()),
          "invalid token fails through C ABI");
  std::puts("LLGUIDANCE_CAPI_OK");
}

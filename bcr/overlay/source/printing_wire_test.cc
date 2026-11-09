// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "mojo/core/embedder/embedder.h"
#include "printing/backend/mojom/print_backend.mojom.h"
#include "printing/backend/print_backend.h"
#include "ui/gfx/geometry/size.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: printing %s\n", message);
    std::exit(1);
  }
}

bool RoundTrip(printing::PrinterSemanticCapsAndDefaults& input,
               printing::PrinterSemanticCapsAndDefaults& output) {
  const auto bytes = printing::mojom::PrinterSemanticCapsAndDefaults::Serialize(&input);
  return printing::mojom::PrinterSemanticCapsAndDefaults::Deserialize(bytes, &output);
}
}  // namespace

int main(int argc, char** argv) {
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  Require(base::FeatureList::InitInstance("", ""), "default features");
  mojo::core::Init();
  using Caps = printing::PrinterSemanticCapsAndDefaults;
  const Caps::Paper first("A", "Z", gfx::Size(210000, 297000));
  const Caps::Paper second("B", "A", gfx::Size(215900, 279400));
  Caps input, output;
  input.papers = {first, first};
  input.default_paper = first;
  input.user_defined_papers = {first, second};
  Require(RoundTrip(input, output) && output.user_defined_papers == input.user_defined_papers
              && output.papers == input.papers,
          "crossed identities preserve distinct papers and allowed standard duplicates");
  input.user_defined_papers = {second, first};
  Require(RoundTrip(input, output) && output.user_defined_papers == input.user_defined_papers,
          "paper identity ordering is independent of insertion order");
  input.user_defined_papers = {first, Caps::Paper("A", "Z", gfx::Size(200000, 250000))};
  Require(!RoundTrip(input, output), "same display name and vendor reject duplicate identity");
  std::puts("PRINTING_WIRE_COMPARATOR_OK");
}

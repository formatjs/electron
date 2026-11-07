// SPDX-License-Identifier: MIT
#include "electron/fuses.h"

int main() {
  using namespace electron::fuses;
  const char sentinel[] = "dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX";
  for (unsigned i = 0; i < sizeof(sentinel) - 1; ++i) {
    if (kFuseWire[i] != sentinel[i]) return 1;
  }
  if (kFuseWire[sizeof(sentinel) - 1] != 1 ||
      kFuseWire[sizeof(sentinel)] != 8) return 2;
  if (!IsRunAsNodeEnabled() || IsCookieEncryptionEnabled() ||
      !IsNodeOptionsEnabled() || !IsNodeCliInspectEnabled() ||
      IsEmbeddedAsarIntegrityValidationEnabled() || IsOnlyLoadAppFromAsarEnabled() ||
      IsLoadBrowserProcessSpecificV8SnapshotEnabled() ||
      !IsGrantFileProtocolExtraPrivilegesEnabled()) return 3;
  return 0;
}

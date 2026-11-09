// SPDX-License-Identifier: MIT
#include "source/asar_path_resolver.h"

#include <iostream>
#include <string>

#include "base/values.h"

int main() {
  base::Value::Dict files;
  base::Value::Dict contents;
  contents.Set("addon.node", base::Value::Dict().Set("unpacked", true).Set("size", 7));
  files.Set("native", base::Value::Dict().Set("files", std::move(contents)));
  files.Set("directory", base::Value::Dict().Set("link", "native"));
  files.Set("alias.node", base::Value::Dict().Set("link", "directory/addon.node"));
  files.Set("chain.node", base::Value::Dict().Set("link", "alias.node"));
  files.Set("root", base::Value::Dict().Set("link", ""));
  files.Set("cycle-a", base::Value::Dict().Set("link", "cycle-b"));
  files.Set("cycle-b", base::Value::Dict().Set("link", "cycle-a"));
  files.Set("directory-cycle", base::Value::Dict().Set("link", "directory-cycle/subdir"));
  files.Set("escape", base::Value::Dict().Set("link", "../outside"));
  files.Set("C:", base::Value::Dict().Set("files", base::Value::Dict().Set("addon.node", base::Value::Dict().Set("unpacked", true))));
  base::Value::Dict root;
  root.Set("files", std::move(files));
  const auto* target = root.FindDict("files")->FindDict("native")->FindDict("files")->FindDict("addon.node");
  for (const auto* path : {"native/addon.node", "directory/addon.node", "alias.node",
                          "chain.node", "root/directory/addon.node", "root/root/chain.node"}) {
    std::string canonical;
    if (asar::internal::ResolveArchivePath(root, path, "/", true, &canonical) != target ||
        canonical != "native/addon.node") {
      std::cerr << "ASAR canonical path mismatch\n";
      return 1;
    }
  }
  std::string canonical;
  if (asar::internal::ResolveArchivePath(root, "root", "/", true, &canonical) != &root ||
      !canonical.empty())
    return 2;
  const auto* link = asar::internal::ResolveArchivePath(root, "alias.node", "/", false, &canonical);
  if (!link || !link->FindString("link") || canonical != "alias.node")
    return 3;
  if (asar::internal::ResolveArchivePath(root, "directory/addon.node", "/", false, &canonical) != target ||
      canonical != "native/addon.node")
    return 4;
  for (const auto* path : {"cycle-a", "directory-cycle/file", "escape", "missing", "native/missing", "/native/addon.node"}) {
    if (asar::internal::ResolveArchivePath(root, path, "/", true, nullptr))
      return 5;
  }
  if (asar::internal::ResolveArchivePath(root, "directory\\addon.node", "\\/", true, &canonical) != target ||
      canonical != "native/addon.node")
    return 6;
  if (asar::internal::ResolveArchivePath(root, "C:\\addon.node", "\\/", true, nullptr))
    return 7;
  std::cout << "ASAR_CANONICAL_PATHS_OK\n";
}

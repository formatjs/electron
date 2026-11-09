// SPDX-License-Identifier: MIT
#ifndef ELECTRON_SHELL_COMMON_ASAR_PATH_RESOLVER_H_
#define ELECTRON_SHELL_COMMON_ASAR_PATH_RESOLVER_H_

#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "base/values.h"

namespace asar::internal {

inline bool SplitArchivePath(std::string_view path,
                             std::string_view separators,
                             std::vector<std::string>* parts) {
  if (!path.empty() && separators.find(path.front()) != std::string_view::npos)
    return false;
  while (!path.empty()) {
    const auto delimiter = path.find_first_of(separators);
    const auto part = path.substr(0, delimiter);
    if (part == ".." || part.find('\0') != std::string_view::npos)
      return false;
    if (!part.empty() && part != ".")
      parts->emplace_back(part);
    if (delimiter == std::string_view::npos)
      break;
    path.remove_prefix(delimiter + 1);
  }
  return true;
}

// ASAR links target archive-root-relative paths, including the empty root path.
inline const base::Value::Dict* ResolveArchivePath(
    const base::Value::Dict& root,
    std::string_view path,
    std::string_view separators,
    bool follow_final,
    std::string* canonical) {
  std::vector<std::string> remaining;
  if (!SplitArchivePath(path, separators, &remaining))
    return nullptr;
  const auto* node = &root;
  std::string resolved;
  unsigned followed = 0;
  for (size_t index = 0; index < remaining.size();) {
    const auto* files = node->FindDict("files");
    if (!files)
      return nullptr;
    const auto& name = remaining[index];
    node = files->FindDict(name);
    if (!node)
      return nullptr;
    if (!resolved.empty())
      resolved += '/';
    resolved += name;
    ++index;
    const auto* link = node->FindString("link");
    if (link && (follow_final || index < remaining.size())) {
      if (++followed > 40)
        return nullptr;
      std::vector<std::string> replacement;
      if (!SplitArchivePath(*link, separators, &replacement))
        return nullptr;
      replacement.insert(replacement.end(), remaining.begin() + index,
                         remaining.end());
      remaining = std::move(replacement);
      index = 0;
      node = &root;
      resolved.clear();
    }
  }
  if (canonical)
    *canonical = std::move(resolved);
  return node;
}

}  // namespace asar::internal

#endif  // ELECTRON_SHELL_COMMON_ASAR_PATH_RESOLVER_H_

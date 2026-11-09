// SPDX-License-Identifier: MIT
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/files/scoped_temp_dir.h"
#include "base/pickle.h"
#include "shell/common/asar/archive.h"

int main() {
  base::ScopedTempDir temporary;
  if (!temporary.CreateUniqueTempDir())
    return 1;
  const auto path = temporary.GetPath().AppendASCII("fixture.asar");
  const auto sidecar = path.AddExtension(FILE_PATH_LITERAL("unpacked"));
  const auto canonical = sidecar.AppendASCII("native/addon.node");
  if (!base::CreateDirectory(canonical.DirName()) ||
      !base::WriteFile(canonical, "unpacked"))
    return 2;
  base::Pickle header;
  header.WriteString(R"({"files":{
    "native":{"files":{"addon.node":{"size":8,"unpacked":true}}},
    "directory":{"link":"native"},
    "alias.node":{"link":"directory/addon.node"},
    "chain.node":{"link":"alias.node"},
    "root":{"link":""},
    "packed.bin":{"size":6,"offset":"0"},
    "packed-alias.bin":{"link":"packed.bin"},
    "cycle-a":{"link":"cycle-b"},
    "cycle-b":{"link":"cycle-a"}
  }})");
  base::Pickle size;
  size.WriteUInt32(static_cast<uint32_t>(header.size()));
  std::string contents(reinterpret_cast<const char*>(size.data()), size.size());
  contents.append(reinterpret_cast<const char*>(header.data()), header.size());
  contents += "packed";
  if (!base::WriteFile(path, contents))
    return 3;
  asar::Archive archive(path);
  if (!archive.Init())
    return 4;
  for (const auto* name : {"native/addon.node", "directory/addon.node", "alias.node",
                          "chain.node", "root/chain.node"}) {
    const auto requested = base::FilePath::FromUTF8Unsafe(name);
    asar::Archive::FileInfo info;
    base::FilePath realpath, output;
    if (!archive.GetFileInfo(requested, &info) || !info.unpacked || info.size != 8 ||
        !archive.Realpath(requested, &realpath) || realpath.AsUTF8Unsafe() != "native/addon.node" ||
        !archive.CopyFileOut(requested, &output) || output != canonical)
      return 5;
    std::string bytes;
    if (!base::ReadFileToString(output, &bytes) || bytes != "unpacked")
      return 6;
  }
  base::FilePath output;
  if (!archive.CopyFileOut(base::FilePath::FromUTF8Unsafe("chain.node"), &output) ||
      !base::WriteFile(output, "same identity"))
    return 7;
  std::string bytes;
  if (!base::ReadFileToString(canonical, &bytes) || bytes != "same identity" ||
      base::PathExists(sidecar.AppendASCII("alias.node")) ||
      base::PathExists(sidecar.AppendASCII("directory")))
    return 8;
  base::FilePath packed, alias;
  if (!archive.CopyFileOut(base::FilePath::FromUTF8Unsafe("packed.bin"), &packed) ||
      !archive.CopyFileOut(base::FilePath::FromUTF8Unsafe("packed-alias.bin"), &alias) ||
      packed != alias || !base::ReadFileToString(alias, &bytes) || bytes != "packed")
    return 9;
  asar::Archive::Stats stat;
  if (!archive.Stat(base::FilePath::FromUTF8Unsafe("alias.node"), &stat) ||
      stat.type != asar::Archive::FileType::kLink)
    return 10;
  std::vector<base::FilePath> entries;
  if (!archive.Readdir(base::FilePath::FromUTF8Unsafe("directory"), &entries) ||
      entries.size() != 1 || entries[0].AsUTF8Unsafe() != "addon.node")
    return 11;
  asar::Archive::FileInfo info;
  if (archive.Realpath(base::FilePath::FromUTF8Unsafe("cycle-a"), &output) ||
      archive.GetFileInfo(base::FilePath::FromUTF8Unsafe("cycle-a"), &info) ||
      archive.CopyFileOut(base::FilePath::FromUTF8Unsafe("cycle-a"), &output))
    return 12;
  std::cout << "ASAR_READER_SIDECAR_ALIASES_OK\n";
}

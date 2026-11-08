// SPDX-License-Identifier: MIT
// Launch declared Python plugins without a shell or host interpreter lookup.
#include <unistd.h>

#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

int main(int argc, char** argv) {
  std::ifstream input(std::string(argv[0]) + ".argv", std::ios::binary);
  std::string contents((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
  if (!input.is_open() || contents.empty() || contents.size() > 65536 || contents.back() != '\0') {
    std::cerr << "Python plugin launcher: invalid argument file\n";
    return 2;
  }
  input.close();
  std::vector<std::string> prefix;
  for (size_t start = 0; start < contents.size();) {
    size_t end = contents.find('\0', start);
    prefix.push_back(contents.substr(start, end - start));
    start = end + 1;
  }
  if (prefix.size() < 2 || prefix.front().empty()) {
    std::cerr << "Python plugin launcher: invalid argument prefix\n";
    return 2;
  }
  std::vector<char*> arguments;
  for (auto& value : prefix) arguments.push_back(value.data());
  for (int index = 1; index < argc; ++index) arguments.push_back(argv[index]);
  arguments.push_back(nullptr);
  execv(arguments.front(), arguments.data());
  std::cerr << "Python plugin launcher: interpreter execution failed\n";
  return 127;
}

// SPDX-License-Identifier: MIT
int gn_source_set_constructor_count = 0;
int GnArchiveApi();
int main() {
  return GnArchiveApi() == 17 && gn_source_set_constructor_count == 1 ? 0 : 1;
}

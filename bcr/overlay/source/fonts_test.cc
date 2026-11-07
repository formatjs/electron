// SPDX-License-Identifier: MIT
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

#include "base/at_exit.h"
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/files/memory_mapped_file.h"
#include "base/files/scoped_temp_dir.h"
#include "base/i18n/icu_util.h"
#include "fontconfig/fontconfig.h"
#include "ft2build.h"
#include FT_FREETYPE_H
#include "hb.h"
#include "hb-ot.h"
#include "libxml/parser.h"
#include "libxml/xpath.h"
#include "third_party/libpng/png.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: fonts %s\n", message);
    std::exit(1);
  }
}

void CheckFonts(const char* path) {
  hb_blob_t* blob = hb_blob_create_from_file_or_fail(path);
  Require(blob && hb_blob_get_length(blob) > 0, "declared font bytes");
  hb_face_t* face = hb_face_create(blob, 0);
  hb_font_t* font = hb_font_create(face);
  hb_ot_font_set_funcs(font);
  hb_font_set_scale(font, hb_face_get_upem(face), hb_face_get_upem(face));
  hb_buffer_t* buffer = hb_buffer_create();
  hb_buffer_add_utf8(buffer, "ffi", 3, 0, 3);
  hb_buffer_set_direction(buffer, HB_DIRECTION_LTR);
  hb_buffer_set_script(buffer, HB_SCRIPT_LATIN);
  hb_buffer_set_language(buffer, hb_language_from_string("en", -1));
  hb_shape(font, buffer, nullptr, 0);
  unsigned count;
  const hb_glyph_info_t* info = hb_buffer_get_glyph_infos(buffer, &count);
  const hb_glyph_position_t* positions = hb_buffer_get_glyph_positions(buffer, nullptr);
  hb_codepoint_t ligature;
  // Original HarfBuzz fixture: ffi forms f_f_i with advance 795.
  Require(hb_font_get_glyph_from_name(font, "f_f_i", -1, &ligature), "fixture ligature glyph");
  Require(count == 1 && info[0].codepoint == ligature && info[0].cluster == 0 && positions[0].x_advance == 795, "original ligature shaping vector");

  hb_buffer_clear_contents(buffer);
  hb_buffer_add_utf8(buffer, "ffi", 3, 0, 3);
  hb_buffer_set_direction(buffer, HB_DIRECTION_LTR);
  hb_buffer_set_script(buffer, HB_SCRIPT_LATIN);
  hb_buffer_set_language(buffer, hb_language_from_string("en", -1));
  hb_feature_t feature;
  Require(hb_feature_from_string("liga=0", -1, &feature), "ligature feature parsing");
  hb_shape(font, buffer, &feature, 1);
  info = hb_buffer_get_glyph_infos(buffer, &count);
  positions = hb_buffer_get_glyph_positions(buffer, nullptr);
  Require(count == 3 && info[0].cluster == 0 && info[1].cluster == 1 && info[2].cluster == 2 && positions[0].x_advance == 300 && positions[1].x_advance == 300 && positions[2].x_advance == 263, "disabled ligature shaping vector");

  FT_Library library;
  FT_Face raster_face;
  Require(FT_Init_FreeType(&library) == 0 && FT_New_Face(library, path, 0, &raster_face) == 0, "FreeType declared font loading");
  Require(FT_Set_Pixel_Sizes(raster_face, 0, 32) == 0 && FT_Load_Glyph(raster_face, ligature, FT_LOAD_RENDER) == 0, "shaped ligature rasterization");
  const auto& bitmap = raster_face->glyph->bitmap;
  bool ink = false;
  for (unsigned row = 0; row < bitmap.rows; ++row)
    for (unsigned col = 0; col < bitmap.width; ++col)
      ink |= bitmap.buffer[row * bitmap.pitch + col] != 0;
  Require(ink, "nonempty ligature pixels");
  const FT_Byte invalid[] = {0, 1, 2, 3};
  FT_Face rejected;
  Require(FT_New_Memory_Face(library, invalid, sizeof(invalid), 0, &rejected) != 0, "invalid font rejection");
  FT_Done_Face(raster_face);
  FT_Done_FreeType(library);
  hb_buffer_destroy(buffer);
  hb_font_destroy(font);
  hb_face_destroy(face);
  hb_blob_destroy(blob);
}

void CheckPng() {
  const std::array<unsigned char, 16> pixels = {255, 0, 0, 255, 0, 255, 0, 127, 0, 0, 255, 0, 19, 31, 47, 255};
  png_image image{};
  image.version = PNG_IMAGE_VERSION;
  image.width = 2;
  image.height = 2;
  image.format = PNG_FORMAT_RGBA;
  png_alloc_size_t size = 0;
  Require(png_image_write_to_memory(&image, nullptr, &size, 0, pixels.data(), 0, nullptr) != 0, "PNG encoded size");
  std::vector<unsigned char> encoded(size);
  Require(png_image_write_to_memory(&image, encoded.data(), &size, 0, pixels.data(), 0, nullptr) != 0, "PNG memory encoding");
  png_image decoded{};
  decoded.version = PNG_IMAGE_VERSION;
  Require(png_image_begin_read_from_memory(&decoded, encoded.data(), size) != 0 && decoded.width == 2 && decoded.height == 2, "PNG dimensions");
  decoded.format = PNG_FORMAT_RGBA;
  std::array<unsigned char, 16> output;
  Require(png_image_finish_read(&decoded, nullptr, output.data(), 0, nullptr) != 0 && output == pixels, "RGBA alpha roundtrip");
  png_image_free(&decoded);
  encoded[0] ^= 1;
  decoded = {};
  decoded.version = PNG_IMAGE_VERSION;
  Require(png_image_begin_read_from_memory(&decoded, encoded.data(), size) == 0, "invalid PNG rejection");
  png_image_free(&decoded);
  png_image_free(&image);
}

void CheckFontconfig(const char* path) {
  Require(std::getenv("FC_FONTATIONS") && std::strcmp(std::getenv("FC_FONTATIONS"), "1") == 0, "original fontations scanner selection");
  FcConfig* config = FcConfigCreate();
  Require(config != nullptr, "isolated Fontconfig creation");
  const FcFontSet* system = FcConfigGetFonts(config, FcSetSystem);
  Require(!system || system->nfont == 0, "empty system font inventory");
  Require(FcConfigAppFontAddFile(config, reinterpret_cast<const FcChar8*>(path)), "Rust fontations declared font scan");
  FcFontSet* application = FcConfigGetFonts(config, FcSetApplication);
  Require(application && application->nfont == 1, "one declared application font");
  FcChar8* family;
  FcChar8* file;
  FcCharSet* charset;
  Require(FcPatternGetString(application->fonts[0], FC_FAMILY, 0, &family) == FcResultMatch && family[0] != 0, "Rust font family metadata");
  Require(FcPatternGetString(application->fonts[0], FC_FILE, 0, &file) == FcResultMatch && base::MakeAbsoluteFilePath(base::FilePath(reinterpret_cast<const char*>(file))) == base::MakeAbsoluteFilePath(base::FilePath(path)), "declared font file identity");
  Require(FcPatternGetCharSet(application->fonts[0], FC_CHARSET, 0, &charset) == FcResultMatch && FcCharSetHasChar(charset, 'f') && FcCharSetHasChar(charset, 'i'), "Rust font character coverage");
  FcPattern* query = FcPatternCreate();
  Require(query && FcPatternAddString(query, FC_FAMILY, family), "font match query");
  FcResult result;
  FcPattern* match = FcFontMatch(config, query, &result);
  Require(match && result == FcResultMatch && FcPatternGetString(match, FC_FILE, 0, &file) == FcResultMatch && base::MakeAbsoluteFilePath(base::FilePath(reinterpret_cast<const char*>(file))) == base::MakeAbsoluteFilePath(base::FilePath(path)), "isolated native font matching");
  FcPatternDestroy(match);
  FcPatternDestroy(query);
  base::ScopedTempDir temporary;
  Require(temporary.CreateUniqueTempDir(), "invalid font scratch directory");
  const auto invalid = temporary.GetPath().AppendASCII("invalid.ttf");
  Require(base::WriteFile(invalid, std::string_view("bad font")), "invalid font fixture write");
  Require(!FcConfigAppFontAddFile(config, reinterpret_cast<const FcChar8*>(invalid.value().c_str())), "Rust invalid font rejection");
  Require(FcConfigGetFonts(config, FcSetApplication)->nfont == 1, "invalid font preserves inventory");
  FcConfigAppFontClear(config);
  application = FcConfigGetFonts(config, FcSetApplication);
  Require(!application || application->nfont == 0, "application font cleanup");
  FcConfigDestroy(config);
}

void CheckXml() {
  constexpr char document[] = "<root><item id='1'>caf\xc3\xa9 &amp; tea</item><item id='2'/></root>";
  xmlDocPtr parsed = xmlReadMemory(document, sizeof(document) - 1, "declared.xml", "UTF-8", XML_PARSE_NONET);
  Require(parsed != nullptr, "XML UTF8 parsing");
  xmlXPathContextPtr context = xmlXPathNewContext(parsed);
  xmlXPathObjectPtr result = xmlXPathEvalExpression(BAD_CAST "count(/root/item)", context);
  Require(result && result->type == XPATH_NUMBER && result->floatval == 2, "native XPath selection");
  xmlChar* content = xmlNodeGetContent(xmlDocGetRootElement(parsed)->children);
  Require(content && std::strcmp(reinterpret_cast<char*>(content), "caf\xc3\xa9 & tea") == 0, "XML UTF8 and entity bytes");
  xmlFree(content);
  xmlXPathFreeObject(result);
  xmlXPathFreeContext(context);
  xmlFreeDoc(parsed);
  constexpr char malformed[] = "<root><item></root>";
  Require(xmlReadMemory(malformed, sizeof(malformed) - 1, "invalid.xml", "UTF-8", XML_PARSE_NONET | XML_PARSE_NOERROR | XML_PARSE_NOWARNING) == nullptr, "malformed XML rejection");
  xmlCleanupParser();
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 3, "declared ICU and font arguments");
  base::AtExitManager at_exit;
  base::File data(base::MakeAbsoluteFilePath(base::FilePath(argv[1])), base::File::FLAG_OPEN | base::File::FLAG_READ);
  Require(data.IsValid() && base::i18n::InitializeICUWithFileDescriptor(data.TakePlatformFile(), base::MemoryMappedFile::Region::kWholeFile), "declared ICU initialization");
  CheckFonts(argv[2]);
  CheckFontconfig(argv[2]);
  CheckPng();
  CheckXml();
}

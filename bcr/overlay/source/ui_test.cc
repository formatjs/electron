// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <string>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/files/memory_mapped_file.h"
#include "base/files/scoped_temp_dir.h"
#include "base/path_service.h"
#include "base/i18n/icu_util.h"
#include "base/task/single_thread_task_executor.h"
#include "third_party/skia/include/core/SkColor.h"
#include "ui/base/resource/resource_bundle.h"
#include "ui/base/resource/resource_scale_factor.h"
#include "ui/base/ui_base_paths.h"
#include "ui/color/color_id.h"
#include "ui/color/color_mixer.h"
#include "ui/color/color_provider.h"
#include "ui/color/color_transform.h"
#include "ui/strings/grit/ui_strings.h"
#include "ui/webui/resources/grit/webui_resources.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: ui %s\n", message);
    std::exit(1);
  }
}

base::FilePath DeclaredPath(const char* path) {
  auto absolute = base::MakeAbsoluteFilePath(base::FilePath(path));
  Require(!absolute.empty(), "canonical declared resource path");
  return absolute;
}

void CheckResources(char** paths) {
  ui::RegisterPathProvider();
  base::ScopedTempDir locales;
  Require(locales.CreateUniqueTempDir() && base::CopyFile(DeclaredPath(paths[0]), locales.GetPath().AppendASCII("en-US.pak")) && base::CopyFile(DeclaredPath(paths[1]), locales.GetPath().AppendASCII("fr.pak")) && base::PathService::Override(ui::DIR_LOCALES, locales.GetPath()), "relocated declared locale pack directory");
  ui::ResourceBundle resources(nullptr);
  Require(resources.ReloadLocaleResources("en-US") == "en-US", "native English locale pack loading");
  Require(resources.GetLocalizedString(IDS_APP_OK) == u"OK" && resources.GetLocalizedString(IDS_APP_CANCEL) == u"Cancel", "original English GRIT resource strings");
  Require(resources.ReloadLocaleResources("fr") == "fr" && resources.GetLocalizedString(IDS_APP_CANCEL) == u"Annuler", "native French locale reload and translation");
  resources.AddDataPackFromPath(DeclaredPath(paths[2]), ui::kScaleFactorNone);
  std::string module;
  Require(base::ReadFileToString(DeclaredPath(paths[3]), &module) && !module.empty(), "declared minified WebUI module");
  Require(resources.LoadDataResourceString(IDR_WEBUI_JS_COLOR_UTILS_JS) == module, "packed WebUI module equals original minifier output");
  base::PathService::RemoveOverride(ui::DIR_LOCALES);
}

void CheckColorPipeline() {
  ui::ColorProvider provider;
  auto& base = provider.AddMixer();
  base[ui::kColorPrimaryBackground] = {SK_ColorBLACK};
  base[ui::kColorPrimaryForeground] = {ui::kColorPrimaryBackground};
  provider.AddMixer()[ui::kColorPrimaryBackground] = {SK_ColorWHITE};
  provider.AddPostprocessingMixer()[ui::kColorPrimaryBackground] =
      ui::GetColorWithMaxContrast(ui::FromTransformInput());
  Require(provider.GetColor(ui::kColorPrimaryBackground) == SK_ColorBLACK && provider.GetColor(ui::kColorPrimaryForeground) == SK_ColorWHITE, "native color overrides aliases and postprocessing");
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 6, "declared ICU and generated resource arguments");
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  Require(base::FeatureList::InitInstance("", ""), "default feature initialization");
  base::SingleThreadTaskExecutor executor;
  base::File data(DeclaredPath(argv[1]), base::File::FLAG_OPEN | base::File::FLAG_READ);
  Require(data.IsValid() && base::i18n::InitializeICUWithFileDescriptor(data.TakePlatformFile(), base::MemoryMappedFile::Region::kWholeFile), "declared ICU initialization");
  CheckResources(argv + 2);
  CheckColorPipeline();
}

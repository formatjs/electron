// SPDX-License-Identifier: MIT
#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "cc/layers/layer.h"
#include "cc/paint/paint_flags.h"
#include "cc/paint/paint_op.h"
#include "cc/paint/paint_op_buffer.h"
#include "cc/paint/paint_record.h"
#include "third_party/skia/include/core/SkBitmap.h"
#include "third_party/skia/include/core/SkCanvas.h"
#include "ui/gfx/geometry/point_f.h"
#include "ui/gfx/geometry/size.h"
#include "ui/gfx/geometry/transform.h"

namespace {
void Require(bool condition, const char* check) {
  if (!condition) {
    std::fprintf(stderr, "check failed: compositor %s\n", check);
    std::exit(1);
  }
}

void CheckLayers() {
  auto root = cc::Layer::Create();
  auto child = cc::Layer::Create();
  auto replacement = cc::Layer::Create();
  root->AddChild(child);
  Require(root->id() != child->id() && child->parent() == root.get() &&
              child->RootLayer() == root.get() && root->children().size() == 1,
          "layer ownership and unique identities");
  child->SetBounds(gfx::Size(8, 6));
  child->SetPosition(gfx::PointF(2, 3));
  child->SetOpacity(0.5f);
  gfx::Transform transform;
  transform.Scale(2, 3);
  child->SetTransform(transform);
  Require(child->bounds() == gfx::Size(8, 6) &&
              child->position() == gfx::PointF(2, 3) &&
              child->opacity() == 0.5f && child->transform() == transform,
          "layer geometry opacity and transform");
  root->ReplaceChild(child.get(), replacement);
  Require(!child->parent() && replacement->parent() == root.get() &&
              root->children().size() == 1 &&
              root->children()[0].get() == replacement.get(),
          "layer replacement detaches previous child");
  child->AddChild(replacement);
  Require(root->children().empty() && replacement->parent() == child.get(),
          "reparenting removes previous ownership");
  child->RemoveAllChildren();
  Require(!replacement->parent() && child->children().empty(),
          "layer teardown removes parent links");
}

void CheckRaster() {
  cc::PaintOpBuffer buffer;
  buffer.push<cc::DrawColorOp>(SkColors::kBlue, SkBlendMode::kSrc);
  buffer.push<cc::SaveOp>();
  buffer.push<cc::ClipRectOp>(SkRect::MakeXYWH(1, 1, 4, 4),
                              SkClipOp::kIntersect, false);
  buffer.push<cc::TranslateOp>(2.f, 2.f);
  cc::PaintFlags flags;
  flags.setAntiAlias(false);
  flags.setColor(SkColors::kRed);
  buffer.push<cc::DrawRectOp>(SkRect::MakeWH(4, 4), flags);
  buffer.push<cc::SaveLayerAlphaOp>(0.5f);
  flags.setColor(SkColors::kGreen);
  buffer.push<cc::DrawRectOp>(SkRect::MakeWH(2, 2), flags);
  buffer.push<cc::RestoreOp>();
  buffer.push<cc::RestoreOp>();
  flags.setColor(SkColors::kWhite);
  buffer.push<cc::DrawRectOp>(SkRect::MakeWH(1, 1), flags);
  auto record = buffer.ReleaseAsRecord();
  Require(buffer.empty() && !record.empty(), "paint record takes buffer ownership");

  SkBitmap bitmap;
  Require(bitmap.tryAllocN32Pixels(8, 8), "declared raster surface allocation");
  SkCanvas canvas(bitmap);
  const int saves = canvas.getSaveCount();
  record.Playback(&canvas);
  Require(canvas.getSaveCount() == saves && canvas.getTotalMatrix().isIdentity(),
          "playback restores canvas state");
  for (int y = 0; y < 8; ++y) {
    for (int x = 0; x < 8; ++x) {
      const SkColor pixel = bitmap.getColor(x, y);
      if (x >= 2 && x < 4 && y >= 2 && y < 4) {
        Require(SkColorGetA(pixel) == 255 && SkColorGetB(pixel) == 0 &&
                    std::abs(int(SkColorGetR(pixel)) - 127) <= 1 &&
                    std::abs(int(SkColorGetG(pixel)) - 128) <= 1,
                "save layer blends green over red");
      } else {
        const SkColor expected = x == 0 && y == 0 ? SK_ColorWHITE :
            x >= 2 && x < 5 && y >= 2 && y < 5 ? SK_ColorRED : SK_ColorBLUE;
        Require(pixel == expected, "raster respects clip translation and restore");
      }
    }
  }
}
}  // namespace

int main(int argc, char** argv) {
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  base::FeatureList::InitInstance("", "");
  CheckLayers();
  CheckRaster();
  std::puts("compositor layer and raster checks passed");
}

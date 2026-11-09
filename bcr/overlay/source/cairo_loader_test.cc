#include <cairo.h>

int main() {
  cairo_surface_t* surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 8, 8);
  cairo_t* context = cairo_create(surface);
  cairo_set_source_rgb(context, 0.25, 0.5, 0.75);
  cairo_paint(context);
  const bool valid = cairo_status(context) == CAIRO_STATUS_SUCCESS &&
                     cairo_surface_status(surface) == CAIRO_STATUS_SUCCESS;
  cairo_destroy(context);
  cairo_surface_destroy(surface);
  return valid ? 0 : 1;
}

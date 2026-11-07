// SPDX-License-Identifier: MIT
#include <dlfcn.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "EGL/egl.h"
#include "EGL/eglext.h"
#include "GLES2/gl2.h"

namespace {
void Require(bool condition, const char* check) {
  if (!condition) {
    std::fprintf(stderr, "check failed: platform_graphics %s\n", check);
    std::exit(1);
  }
}

void Stage(const char* stage) {
  std::fprintf(stderr, "[DEBUG-native-graphics] %s\n", stage);
}

void* Open(const char* path) {
  void* library = dlopen(path, RTLD_NOW | RTLD_LOCAL);
  if (!library) std::fprintf(stderr, "[DEBUG-native-graphics] dlopen: %s\n", dlerror());
  Require(library != nullptr, "source-built graphics library loading");
  return library;
}

template <typename T>
T Symbol(void* library, const char* name) {
  auto symbol = reinterpret_cast<T>(dlsym(library, name));
  Require(symbol != nullptr, "original EGL and GLES exports");
  return symbol;
}
}  // namespace

int main(int argc, char** argv) {
  Stage("entry");
  Require(argc == 3, "declared graphics library arguments");
  void* egl = Open(argv[1]);
  Stage("egl");
  void* gles = Open(argv[2]);
  Stage("gles");
  Require(egl && gles, "source-built graphics library loading");
  auto query = Symbol<decltype(&eglQueryString)>(egl, "eglQueryString");
  auto get = Symbol<decltype(&eglGetProcAddress)>(egl, "eglGetProcAddress");
  const char* extensions = query(EGL_NO_DISPLAY, EGL_EXTENSIONS);
  Require(extensions && std::strstr(extensions, "EGL_ANGLE_platform_angle"),
          "native ANGLE client dispatch");
  auto platform = reinterpret_cast<PFNEGLGETPLATFORMDISPLAYEXTPROC>(
      get("eglGetPlatformDisplayEXT"));
  Require(platform != nullptr, "native ANGLE platform entry");
  Stage("platform");
  const EGLint display_attributes[] = {
      EGL_PLATFORM_ANGLE_TYPE_ANGLE, EGL_PLATFORM_ANGLE_TYPE_VULKAN_ANGLE,
      EGL_PLATFORM_ANGLE_DEVICE_TYPE_ANGLE,
      EGL_PLATFORM_ANGLE_DEVICE_TYPE_SWIFTSHADER_ANGLE, EGL_NONE};
  EGLDisplay display = platform(EGL_PLATFORM_ANGLE_ANGLE, nullptr,
                                display_attributes);
  EGLint major = 0, minor = 0;
  Require(display != EGL_NO_DISPLAY &&
              Symbol<decltype(&eglInitialize)>(egl, "eglInitialize")(
                  display, &major, &minor) == EGL_TRUE,
          "source SwiftShader display initialization");
  Stage("display");
  Require(Symbol<decltype(&eglBindAPI)>(egl, "eglBindAPI")(
              EGL_OPENGL_ES_API) == EGL_TRUE,
          "native GLES API binding");
  const EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                               EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                               EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8,
                               EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
  EGLConfig config = nullptr;
  EGLint count = 0;
  Require(Symbol<decltype(&eglChooseConfig)>(egl, "eglChooseConfig")(
              display, attributes, &config, 1, &count) == EGL_TRUE && count == 1,
          "native software framebuffer configuration");
  const EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
  EGLContext context = Symbol<decltype(&eglCreateContext)>(egl, "eglCreateContext")(
      display, config, EGL_NO_CONTEXT, context_attributes);
  const EGLint surface_attributes[] = {EGL_WIDTH, 2, EGL_HEIGHT, 2, EGL_NONE};
  EGLSurface surface = Symbol<decltype(&eglCreatePbufferSurface)>(
      egl, "eglCreatePbufferSurface")(display, config, surface_attributes);
  auto make_current = Symbol<decltype(&eglMakeCurrent)>(egl, "eglMakeCurrent");
  Require(context != EGL_NO_CONTEXT && surface != EGL_NO_SURFACE &&
              make_current(display, surface, surface, context) == EGL_TRUE,
          "native software rendering context");
  Stage("context");
  const auto* renderer = Symbol<decltype(&glGetString)>(gles, "glGetString")(
      GL_RENDERER);
  Require(renderer && std::strstr(reinterpret_cast<const char*>(renderer),
                                 "SwiftShader"),
          "explicit software renderer selection");
  Symbol<decltype(&glClearColor)>(gles, "glClearColor")(1.0f, 0.0f, 0.0f, 1.0f);
  Symbol<decltype(&glClear)>(gles, "glClear")(GL_COLOR_BUFFER_BIT);
  unsigned char pixels[16] = {};
  Symbol<decltype(&glReadPixels)>(gles, "glReadPixels")(
      0, 0, 2, 2, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
  Require(Symbol<decltype(&glGetError)>(gles, "glGetError")() == GL_NO_ERROR,
          "native software pixel readback");
  for (int pixel = 0; pixel < 4; ++pixel) {
    Require(pixels[pixel * 4] == 255 && pixels[pixel * 4 + 1] == 0 &&
                pixels[pixel * 4 + 2] == 0 && pixels[pixel * 4 + 3] == 255,
            "source software framebuffer bytes");
  }
  Stage("render");
  Require(make_current(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT) ==
                  EGL_TRUE &&
              Symbol<decltype(&eglDestroySurface)>(egl, "eglDestroySurface")(
                  display, surface) == EGL_TRUE &&
              Symbol<decltype(&eglDestroyContext)>(egl, "eglDestroyContext")(
                  display, context) == EGL_TRUE &&
              Symbol<decltype(&eglTerminate)>(egl, "eglTerminate")(display) ==
                  EGL_TRUE,
          "native graphics resource teardown");
  Stage("teardown");
  dlclose(gles);
  dlclose(egl);
  Stage("done");
}

// SPDX-License-Identifier: MIT
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <dlfcn.h>
#include <elf.h>
#include <ucontext.h>
#include <unwind.h>
#include <unistd.h>

#include <csignal>
#include <cstdint>

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "EGL/egl.h"
#include "EGL/eglext.h"
#include "GLES2/gl2.h"
#include "vulkan/vulkan.h"

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

void FrameAddress(uintptr_t address) {
  Dl_info info = {};
  if (dladdr(reinterpret_cast<void*>(address), &info) && info.dli_fname) {
    const auto* header = static_cast<const Elf64_Ehdr*>(info.dli_fbase);
    const uintptr_t offset = header->e_type == ET_EXEC ? address :
        address - reinterpret_cast<uintptr_t>(info.dli_fbase);
    std::fprintf(stderr, "[DEBUG-native-graphics] frame %s 0x%lx\n",
                 info.dli_fname, static_cast<unsigned long>(offset));
  }
}

_Unwind_Reason_Code Frame(_Unwind_Context* context, void* data) {
  auto* count = static_cast<unsigned*>(data);
  if ((*count)++ >= 24) return _URC_END_OF_STACK;
  FrameAddress(static_cast<uintptr_t>(_Unwind_GetIP(context)));
  return _URC_NO_REASON;
}

void Crash(int signal, siginfo_t*, void* data) {
  std::fprintf(stderr, "[DEBUG-native-graphics] signal %d\n", signal);
  const auto* context = static_cast<const ucontext_t*>(data);
  const auto address = static_cast<uintptr_t>(context->uc_mcontext.gregs[REG_RIP]);
  const auto stack = static_cast<uintptr_t>(context->uc_mcontext.gregs[REG_RSP]);
  std::fprintf(stderr, "[DEBUG-native-graphics] fault_pc %s\n", address ? "nonzero" : "zero");
  FrameAddress(address);
  if (stack) FrameAddress(*reinterpret_cast<const uintptr_t*>(stack));
  unsigned count = 0;
  _Unwind_Backtrace(Frame, &count);
  _exit(128 + signal);
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
  struct sigaction action = {};
  action.sa_sigaction = Crash;
  action.sa_flags = SA_SIGINFO;
  sigemptyset(&action.sa_mask);
  sigaction(SIGSEGV, &action, nullptr);
  Stage("entry");
  Require(argc == 4, "declared graphics library arguments");
  void* vulkan = Open(argv[3]);
  auto get_instance = reinterpret_cast<PFN_vkGetInstanceProcAddr>(
      dlsym(vulkan, "vkGetInstanceProcAddr"));
  Require(get_instance != nullptr, "source Vulkan loader export");
  Require(get_instance(VK_NULL_HANDLE, "vkCreateInstance") != nullptr,
          "source Vulkan loader dispatch");
  Stage("vulkan");
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
  Stage("display_handle");
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
  dlclose(vulkan);
  Stage("done");
}

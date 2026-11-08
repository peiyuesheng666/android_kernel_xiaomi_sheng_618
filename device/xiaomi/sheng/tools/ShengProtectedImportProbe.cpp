// SPDX-License-Identifier: Apache-2.0
// Allocate empty offscreen buffers and test protected EGL import. No camera,
// image acquisition, CPU mapping, texture sampling, drawing or readback.
#define EGL_EGLEXT_PROTOTYPES
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <hardware/gralloc.h>
#include <ui/GraphicBuffer.h>

#include <cstdio>
#include <cstring>
#include <string>

namespace {
bool hasExtension(const char* extensions, const char* name) {
    if (!extensions) return false;
    const std::string list = std::string(" ") + extensions + " ";
    return list.find(std::string(" ") + name + " ") != std::string::npos;
}
}

int main() {
    setvbuf(stdout, nullptr, _IONBF, 0);
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint major = 0, minor = 0;
    if (display == EGL_NO_DISPLAY || !eglInitialize(display, &major, &minor)) {
        std::printf("egl_initialize_failed=0x%x\n", eglGetError());
        return 1;
    }
    const char* extensions = eglQueryString(display, EGL_EXTENSIONS);
    std::printf("egl_version=%d.%d vendor=%s protected_content=%d native_buffer=%d\n",
                major, minor, eglQueryString(display, EGL_VENDOR),
                hasExtension(extensions, "EGL_EXT_protected_content"),
                hasExtension(extensions, "EGL_ANDROID_image_native_buffer"));
    if (!hasExtension(extensions, "EGL_EXT_protected_content") ||
        !hasExtension(extensions, "EGL_ANDROID_image_native_buffer")) return 2;
    const EGLint configAttrs[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
            EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8,
            EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE};
    EGLConfig config = nullptr;
    EGLint count = 0;
    if (!eglBindAPI(EGL_OPENGL_ES_API) ||
        !eglChooseConfig(display, configAttrs, &config, 1, &count) || count != 1) return 3;

    constexpr uint64_t gpu = GRALLOC_USAGE_HW_TEXTURE | GRALLOC_USAGE_HW_COMPOSER;
    struct Case { const char* name; int format; uint64_t usage; };
    const Case cases[] = {
            {"ordinary_rgba", android::PIXEL_FORMAT_RGBA_8888, gpu},
            {"protected_rgba", android::PIXEL_FORMAT_RGBA_8888, gpu | GRALLOC_USAGE_PROTECTED},
            {"protected_ubwc", 0x7fa30c06, gpu | GRALLOC_USAGE_PROTECTED},
            {"protected_camera_ubwc", 0x7fa30c06,
                    gpu | GRALLOC_USAGE_PROTECTED | GRALLOC_USAGE_HW_CAMERA_WRITE},
    };
    unsigned completed = 0;
    for (const auto& test : cases) {
        const bool protectedContent = test.usage & GRALLOC_USAGE_PROTECTED;
        const EGLint contextAttrs[] = {EGL_CONTEXT_CLIENT_VERSION, 2,
                protectedContent ? EGL_PROTECTED_CONTENT_EXT : EGL_NONE,
                protectedContent ? EGL_TRUE : EGL_NONE, EGL_NONE};
        const EGLint surfaceAttrs[] = {EGL_WIDTH, 1, EGL_HEIGHT, 1,
                protectedContent ? EGL_PROTECTED_CONTENT_EXT : EGL_NONE,
                protectedContent ? EGL_TRUE : EGL_NONE, EGL_NONE};
        EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, contextAttrs);
        EGLSurface surface = eglCreatePbufferSurface(display, config, surfaceAttrs);
        if (context == EGL_NO_CONTEXT || surface == EGL_NO_SURFACE ||
            !eglMakeCurrent(display, surface, surface, context)) {
            std::printf("case=%s context_or_surface_failed=0x%x\n", test.name, eglGetError());
            return 4;
        }
        {
            auto buffer = android::sp<android::GraphicBuffer>::make(640, 480,
                    test.format, 1, test.usage, "sheng-protected-import-probe");
            std::printf("case=%s allocation=%d format=0x%x usage=0x%llx protected=%d\n",
                        test.name, buffer->initCheck(), buffer->getPixelFormat(),
                        static_cast<unsigned long long>(buffer->getUsage()), protectedContent);
            if (buffer->initCheck() != 0 || !buffer->handle) return 5;
            EGLClientBuffer client = eglGetNativeClientBufferANDROID(buffer->toAHardwareBuffer());
            const EGLint imageAttrs[] = {EGL_IMAGE_PRESERVED_KHR, EGL_TRUE,
                    protectedContent ? EGL_PROTECTED_CONTENT_EXT : EGL_NONE,
                    protectedContent ? EGL_TRUE : EGL_NONE, EGL_NONE};
            (void)eglGetError();
            EGLImageKHR image = eglCreateImageKHR(display, EGL_NO_CONTEXT,
                    EGL_NATIVE_BUFFER_ANDROID, client, imageAttrs);
            const EGLint error = eglGetError();
            std::printf("case=%s egl_import=%s error=0x%x\n", test.name,
                        image == EGL_NO_IMAGE_KHR ? "rejected" : "accepted", error);
            if (image != EGL_NO_IMAGE_KHR && !eglDestroyImageKHR(display, image)) return 6;
            // A rejected import is diagnostic evidence, not a successful rendering test.
            ++completed;
        }
        if (!eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT) ||
            !eglDestroySurface(display, surface) || !eglDestroyContext(display, context)) return 7;
    }
    if (!eglTerminate(display)) return 8;
    std::printf("cases_completed=%u camera_opened=false cpu_mapping=false "
                "texture_sampled=false pixels_read=false\n", completed);
    return 0;
}

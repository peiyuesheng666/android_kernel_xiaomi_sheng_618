// SPDX-License-Identifier: Apache-2.0
// Query layout metadata only. Never open a camera or allocate a captured image.
#include <dlfcn.h>
#include <cstdio>

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    void* library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        std::fprintf(stderr, "dlopen: %s\n", dlerror());
        return 3;
    }
    const char* symbols[] = {
        "CamxFormatUtil_GetStrideInBytes", "CamxFormatUtil_GetStrideInPixels",
        "CamxFormatUtil_GetScanline", "CamxFormatUtil_GetPlaneSize",
        "CamxFormatUtil_GetBufferSize", "CamxFormatUtil_GetUBWCInfo",
        "CamxFormatUtil_GetPlaneAlignment", "CamxFormatUtil_GetPlaneOffset",
        "CamxFormatUtil_IsPerPlaneFdNeeded", "CamxFormatUtil_GetBpp",
        "CamxFormatUtil_GetPerPlaneBpp", "CamxFormatUtil_GetSubsamplingFactor",
        "CamxFormatUtil_GetPlaneCount", "CamxFormatUtil_GetPlaneTypes",
        "CamxFormatUtil_GetPixelIncrement", "CamxFormatUtil_GetPlaneStartAddressAlignment",
    };
    for (const char* symbol : symbols) {
        if (!dlsym(library, symbol)) {
            std::fprintf(stderr, "missing export: %s\n", symbol);
            dlclose(library);
            return 4;
        }
    }
    using Stride = int (*)(unsigned int, int, int, int*);
    using Size = int (*)(unsigned int, int, int, unsigned int*);
    const auto stride = reinterpret_cast<Stride>(dlsym(library, symbols[0]));
    const auto scanline = reinterpret_cast<Stride>(dlsym(library, symbols[2]));
    const auto size = reinterpret_cast<Size>(dlsym(library, symbols[4]));
    const int dimensions[][2] = {{1920, 1080}, {640, 480}, {642, 482}};
    for (const auto& dimensions_case : dimensions) {
        const int width = dimensions_case[0], height = dimensions_case[1];
        int y_stride = 0, uv_stride = 0, y_rows = 0, uv_rows = 0;
        unsigned int bytes = 0;
        // CamxPlaneType: Y=1, UV=2, as declared by the installed gralloc ABI.
        if (stride(0x113, 1, width, &y_stride) || stride(0x113, 2, width, &uv_stride) ||
            scanline(0x113, 1, height, &y_rows) || scanline(0x113, 2, height, &uv_rows) ||
            size(0x113, width, height, &bytes) || y_stride < width || uv_stride < width ||
            y_rows < height || uv_rows < height / 2 ||
            bytes < static_cast<unsigned int>(width * height * 3 / 2)) {
            std::fprintf(stderr, "NV21_ZSL layout query failed: %dx%d\n", width, height);
            dlclose(library);
            return 5;
        }
        std::printf("NV21_ZSL=%dx%d stride=%d,%d rows=%d,%d bytes=%u\n",
                    width, height, y_stride, uv_stride, y_rows, uv_rows, bytes);
    }
    dlclose(library);
    std::puts("exports=16 layouts=3 camera_used=false");
    return 0;
}

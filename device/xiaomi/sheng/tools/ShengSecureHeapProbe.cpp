// SPDX-License-Identifier: Apache-2.0
// Validate the existing native DMA heap backend without opening a camera,
// acquiring images, mapping protected pixels or changing global properties.
#include <hardware/gralloc.h>
#include <cstdio>
#include <dlfcn.h>
#include "gr_alloc_interface.h"

int main() {
    setvbuf(stdout, nullptr, _IONBF, 0);
    void* library = dlopen("/vendor/lib64/libgralloccore.so", RTLD_NOW | RTLD_LOCAL);
    if (!library) { std::fprintf(stderr, "%s\n", dlerror()); return 1; }
    using Factory = gralloc::AllocInterface* (*)();
    auto legacyFactory = reinterpret_cast<Factory>(dlsym(library,
            "_ZN7gralloc16DmaLegacyManager11GetInstanceEv"));
    auto nativeFactory = reinterpret_cast<Factory>(dlsym(library,
            "_ZN7gralloc10DmaManager11GetInstanceEv"));
    if (!legacyFactory || !nativeFactory) return 2;
    auto* legacy = legacyFactory();
    auto* native = nativeFactory();
    if (!legacy || !native) return 3;
    for (int preview = 0; preview < 2; ++preview) {
        const uint64_t usage = GRALLOC_USAGE_PROTECTED | GRALLOC_USAGE_HW_CAMERA_WRITE
                | (preview ? GRALLOC_USAGE_HW_COMPOSER | GRALLOC_USAGE_HW_TEXTURE : 0);
        gralloc::AllocData oldData;
        oldData.size = 2 * 1024 * 1024;
        legacy->GetHeapInfo(usage, false, &oldData.heap_name, &oldData.vm_names,
                &oldData.alloc_type, &oldData.flags, &oldData.size);
        std::printf("legacy preview=%d heap=%s ion_flags=0x%x vm_count=%zu metadata_only=true\n",
                preview, oldData.heap_name.c_str(), oldData.flags, oldData.vm_names.size());
        if (oldData.flags == 0 || !oldData.vm_names.empty()) return 4;

        gralloc::AllocData data;
        data.size = 2 * 1024 * 1024;
        data.align = 4096;
        native->GetHeapInfo(usage, false, &data.heap_name, &data.vm_names,
                &data.alloc_type, &data.flags, &data.size);
        std::printf("native preview=%d heap=%s vm_count=%zu\n",
                preview, data.heap_name.c_str(), data.vm_names.size());
        for (const auto& vm : data.vm_names) std::printf("native_vm=%s\n", vm.c_str());
        if (data.heap_name != "qcom,display" || data.vm_names.size() != (preview ? 2u : 1u)) return 5;
        const int allocation = native->AllocBuffer(&data);
        std::printf("native_allocate=%d fd_valid=%d\n", allocation, data.fd >= 0);
        if (allocation != 0 || data.fd < 0) return 6;
        const int lend = native->SecureMemPerms(&data);
        std::printf("native_secure_lend=%d\n", lend);
        const int release = native->FreeBuffer(nullptr, data.size, data.offset, data.fd, data.ion_handle);
        std::printf("native_release=%d\n", release);
        if (lend != 0 || release != 0) return 7;
    }
    std::puts("native_secure_allocations=2 camera_opened=false protected_pixels_mapped=false");
    return 0;
}

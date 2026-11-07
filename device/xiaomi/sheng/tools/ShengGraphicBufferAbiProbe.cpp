// SPDX-License-Identifier: Apache-2.0
// Exercise libui object storage without loading a camera HAL or acquiring images.
#include <ui/GraphicBuffer.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <new>

int main() {
    using android::GraphicBuffer;
    constexpr size_t guard = 64, legacySize = 256;
    const size_t currentSize = sizeof(GraphicBuffer);
    // The non-deleting destructor permits checking both redzones after teardown.
    auto destroy = reinterpret_cast<void (*)(GraphicBuffer*)>(
            dlsym(RTLD_DEFAULT, "_ZN7android13GraphicBufferD1Ev"));
    if (!destroy || currentSize <= legacySize) return 1;
    std::printf("graphic_buffer_bytes=%zu legacy_allocation_bytes=%zu\n", currentSize, legacySize);
    size_t changedTail = 0;
    for (int mode = 0; mode < 2; ++mode) {
        for (int iteration = 0; iteration < 100; ++iteration) {
            auto* storage = static_cast<unsigned char*>(std::malloc(currentSize + 2 * guard));
            if (!storage) return 2;
            std::memset(storage, 0xa5, currentSize + 2 * guard);
            auto* memory = storage + guard;
            GraphicBuffer* buffer = mode == 0
                    ? new (memory) GraphicBuffer()
                    : new (memory) GraphicBuffer(nullptr, GraphicBuffer::WRAP_HANDLE,
                            16, 16, android::PIXEL_FORMAT_RGBA_8888, 1, uint64_t{0}, 16);
            auto redzonesIntact = [&] {
                return std::all_of(storage, memory, [](auto byte) { return byte == 0xa5; })
                        && std::all_of(memory + currentSize, memory + currentSize + guard,
                                [](auto byte) { return byte == 0xa5; });
            };
            size_t changed = std::count_if(memory + legacySize, memory + currentSize,
                    [](auto byte) { return byte != 0xa5; });
            if (!changed || !redzonesIntact()) return 3;
            changedTail = std::max(changedTail, changed);
            destroy(buffer);
            if (!redzonesIntact()) return 4;
            std::free(storage);
        }
        std::printf("mode=%s construction_destruction_cycles=100 redzones=intact\n",
                mode == 0 ? "default" : "null-handle-wrap");
    }
    std::printf("writes_past_legacy_allocation=%zu no_camera_hal_loaded=true\n", changedTail);
    return 0;
}

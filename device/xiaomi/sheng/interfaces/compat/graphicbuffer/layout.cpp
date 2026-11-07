// SPDX-License-Identifier: Apache-2.0
#include <ui/GraphicBuffer.h>
#include <cstddef>

// Only these two complete layouts have been reviewed. Public-source changes
// require a new ABI review instead of silently resizing proprietary objects.
static_assert(sizeof(android::GraphicBuffer) == 256 || sizeof(android::GraphicBuffer) == 3376);
static_assert(alignof(android::GraphicBuffer) == 8);
static_assert(sizeof(android::RefBase) == 16);
static_assert(sizeof(ANativeWindowBuffer) == 168);
static_assert(offsetof(ANativeWindowBuffer, width) == 56);
static_assert(offsetof(ANativeWindowBuffer, handle) == 96);
static_assert(offsetof(ANativeWindowBuffer, usage) == 104);

// A non-LTO ELF symbol records the compiler's actual vendor class size for the
// generated library transform. This archive is never installed or linked.
extern "C" {
__attribute__((used)) unsigned char sheng_graphicbuffer_size[sizeof(android::GraphicBuffer)] = {};
__attribute__((used)) unsigned char sheng_graphicbuffer_alignment[alignof(android::GraphicBuffer)] = {};
}

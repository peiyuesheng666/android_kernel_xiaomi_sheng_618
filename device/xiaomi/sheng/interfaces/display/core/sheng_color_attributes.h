/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SHENG_COLOR_ATTRIBUTES_H_
#define SHENG_COLOR_ATTRIBUTES_H_

#include <array>
#include <cstddef>
#include <cstring>

namespace sheng {

// Stock libsdm-color.so was built before the trailing HWResourceInfo DDR
// version field. Its PPHWAttributes suffix begins at 0x260, not 0x268.
// This is a borrowed ABI view: the copied vector/map pointers remain owned
// by the live source object; the byte buffer must never run their destructors.
struct alignas(8) StockColorAttributes {
  static constexpr size_t kResourceBytes = 0x260;
  static constexpr size_t kRemovedBytes = 8;
  static constexpr size_t kSourceBytes = 0x588;
  static constexpr size_t kStockBytes = kSourceBytes - kRemovedBytes;
  std::array<unsigned char, kStockBytes> bytes{};

  explicit StockColorAttributes(const void *source) {
    const auto *data = static_cast<const unsigned char *>(source);
    std::memcpy(bytes.data(), data, kResourceBytes);
    std::memcpy(bytes.data() + kResourceBytes,
                data + kResourceBytes + kRemovedBytes, kStockBytes - kResourceBytes);
  }
};

}  // namespace sheng
#endif  // SHENG_COLOR_ATTRIBUTES_H_

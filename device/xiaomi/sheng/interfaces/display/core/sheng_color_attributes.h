/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SHENG_COLOR_ATTRIBUTES_H_
#define SHENG_COLOR_ATTRIBUTES_H_

#include <array>
#include <cstddef>
#include <cstring>

namespace sheng {

// Stock libsdm-color.so was built before the trailing HWResourceInfo DDR
// version field. Its PPHWAttributes suffix begins at 0x260, not 0x268.
// Own a real deep copy before compacting the scalar/layout suffix in place.
// A raw borrowed map copy is invalid: its nodes still point at the original
// object's end sentinel. Keeping this copy's prefix at its constructed address
// preserves that sentinel. Restore the native layout before C++ destruction.
template <typename NativeAttributes>
class StockColorAttributes {
 public:
  static constexpr size_t kResourceBytes = 0x260;
  static constexpr size_t kRemovedBytes = 8;
  static constexpr size_t kSourceBytes = 0x588;
  static constexpr size_t kStockBytes = kSourceBytes - kRemovedBytes;
  explicit StockColorAttributes(const NativeAttributes &source) : storage_(source) {
    static_assert(sizeof(NativeAttributes) == kSourceBytes);
    auto *data = reinterpret_cast<unsigned char *>(&storage_);
    std::memcpy(removed_.data(), data + kResourceBytes, kRemovedBytes);
    std::memmove(data + kResourceBytes, data + kResourceBytes + kRemovedBytes,
                 kStockBytes - kResourceBytes);
  }

  ~StockColorAttributes() {
    auto *data = reinterpret_cast<unsigned char *>(&storage_);
    std::memmove(data + kResourceBytes + kRemovedBytes, data + kResourceBytes,
                 kStockBytes - kResourceBytes);
    std::memcpy(data + kResourceBytes, removed_.data(), kRemovedBytes);
  }

  StockColorAttributes(const StockColorAttributes &) = delete;
  StockColorAttributes &operator=(const StockColorAttributes &) = delete;
  StockColorAttributes(StockColorAttributes &&) = delete;
  StockColorAttributes &operator=(StockColorAttributes &&) = delete;

  const NativeAttributes &get() const { return storage_; }

 private:
  NativeAttributes storage_;
  std::array<unsigned char, kRemovedBytes> removed_{};
};

}  // namespace sheng
#endif  // SHENG_COLOR_ATTRIBUTES_H_

#!/usr/bin/env python3
"""Check the exact source-to-stock ABI boundary without loading any driver."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

CORE = Path(__file__).resolve().parents[1] / 'interfaces/display/core'


class ColorAttributesABI(unittest.TestCase):
    def test_owned_containers_and_restored_destruction(self):
        fixture = r'''
#include "sheng_color_attributes.h"
#include <cassert>
#include <cstdint>
#include <map>
#include <vector>
using Formats = std::map<int, std::vector<int>>;
struct Native {
  std::array<unsigned char, 0xf0> prefix{};
  Formats formats;
  std::array<unsigned char, 0x260 - 0xf0 - sizeof(Formats)> resource_tail{};
  uint64_t removed = 0xdecafbad12345678ULL;
  std::vector<uint64_t> bitclocks;
  std::array<unsigned char, 0x588 - 0x268 - sizeof(bitclocks)> suffix{};
};
static_assert(sizeof(Native) == 0x588);
int main() {
 for (int count : {0, 1, 3, 100}) {
  Native source;
  for (int i = 0; i < count; ++i) source.formats[i] = {i, i + 1, i + 2};
  source.bitclocks = {400000, 600000, 800000};
  const std::array<uint32_t, 9> versions = {19,17,5,5,11,7,21,18,16};
  auto *source_data = reinterpret_cast<unsigned char *>(&source);
  std::memcpy(source_data + 0x550, versions.data(), sizeof(versions));
  const uint64_t borrowed_pointer = 0x1234567887654321ULL;
  std::memcpy(source_data + 0x578, &borrowed_pointer, sizeof(borrowed_pointer));
  const uint32_t maximum_brightness = 4095;
  std::memcpy(source_data + 0x580, &maximum_brightness, sizeof(maximum_brightness));
  {
    sheng::StockColorAttributes<Native> stock(source);
    const auto *data = reinterpret_cast<const unsigned char *>(&stock.get());
    const auto &formats = stock.get().formats;
    assert(&formats != &source.formats && formats == source.formats);
    assert((formats.begin() == formats.end()) == (count == 0));
    int seen = 0;
    for (const auto &entry : formats) {
      assert(entry.first == seen && entry.second == source.formats.at(seen));
      assert(&entry != &*source.formats.find(seen));
      ++seen;
    }
    assert(seen == count);
    const auto &stock_bitclocks = *reinterpret_cast<const std::vector<uint64_t> *>(data + 0x260);
    assert(stock_bitclocks == source.bitclocks);
    assert(stock_bitclocks.data() != source.bitclocks.data());
    assert(std::memcmp(data + 0x548, versions.data(), sizeof(versions)) == 0);
    uint32_t dither = 0, brightness = 0;
    uint64_t pointer = 0;
    std::memcpy(&dither, data + 0x55c, sizeof(dither));
    std::memcpy(&pointer, data + 0x570, sizeof(pointer));
    std::memcpy(&brightness, data + 0x578, sizeof(brightness));
    assert(dither == 7 && pointer == borrowed_pointer && brightness == 4095);
  }
  // Both copies were iterated and only the view's own allocations were freed.
  assert(source.formats.size() == static_cast<size_t>(count));
  assert(source.bitclocks == std::vector<uint64_t>({400000, 600000, 800000}));
  assert(source.removed == 0xdecafbad12345678ULL);
 }
}
'''
        with tempfile.TemporaryDirectory(prefix='sheng-color-abi-') as directory:
            source, binary = Path(directory) / 'abi.cpp', Path(directory) / 'abi'
            source.write_text(fixture)
            subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-Wall', '-Wextra',
                            '-Werror', '-fsanitize=address,undefined', '-I', str(CORE),
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()

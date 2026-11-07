#!/usr/bin/env python3
"""Check the exact source-to-stock ABI boundary without loading any driver."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

CORE = Path(__file__).resolve().parents[1] / 'interfaces/display/core'


class ColorAttributesABI(unittest.TestCase):
    def test_borrowed_layout(self):
        fixture = r'''
#include "sheng_color_attributes.h"
#include <cassert>
#include <cstdint>
int main() {
  alignas(8) std::array<unsigned char, 0x588> source;
  for (size_t i = 0; i < source.size(); ++i) source[i] = (i * 37 + i / 256) & 255;
  const std::array<uint32_t, 9> versions = {19,17,5,5,11,7,21,18,16};
  std::memcpy(source.data() + 0x550, versions.data(), sizeof(versions));
  const uint64_t borrowed_pointer = 0x1234567887654321ULL;
  std::memcpy(source.data() + 0x578, &borrowed_pointer, sizeof(borrowed_pointer));
  const uint32_t maximum_brightness = 4095;
  std::memcpy(source.data() + 0x580, &maximum_brightness, sizeof(maximum_brightness));
  const auto before = source;
  {
    sheng::StockColorAttributes stock(source.data());
    static_assert(sizeof(stock) == 0x580 && alignof(decltype(stock)) == 8);
    assert(std::memcmp(stock.bytes.data(), source.data(), 0x260) == 0);
    assert(std::memcmp(stock.bytes.data() + 0x260, source.data() + 0x268, 0x320) == 0);
    assert(std::memcmp(stock.bytes.data() + 0x548, versions.data(), sizeof(versions)) == 0);
    uint32_t dither = 0, brightness = 0;
    uint64_t pointer = 0;
    std::memcpy(&dither, stock.bytes.data() + 0x55c, sizeof(dither));
    std::memcpy(&pointer, stock.bytes.data() + 0x570, sizeof(pointer));
    std::memcpy(&brightness, stock.bytes.data() + 0x578, sizeof(brightness));
    assert(dither == 7 && pointer == borrowed_pointer && brightness == 4095);
  }
  // No source bytes or pointed-to objects are destroyed by the borrowed view.
  assert(source == before);
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

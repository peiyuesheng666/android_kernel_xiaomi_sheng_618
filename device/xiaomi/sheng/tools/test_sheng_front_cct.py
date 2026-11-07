#!/usr/bin/env python3
"""Exercise invalid front-CCT isolation without a sensor or Android service."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
fixture = r'''
#include "ShengCctSample.h"
#include <cassert>
#include <limits>
int main() {
  const int cct = 33171088;
  const char *name = "xiaomi.sensor.front_cct";
  for (float value : {0.0f, -1.0f, std::numeric_limits<float>::infinity(),
                     -std::numeric_limits<float>::infinity(),
                     std::numeric_limits<float>::quiet_NaN()}) {
    assert(sheng::RejectInvalidFrontCct(cct, cct, name, false, value));
    assert(!sheng::RejectInvalidFrontCct(0, cct, name, false, value)); // flush
    assert(!sheng::RejectInvalidFrontCct(33, cct, name, false, value)); // additional info
    assert(!sheng::RejectInvalidFrontCct(cct, cct, name, true, value));
    assert(!sheng::RejectInvalidFrontCct(cct, cct, "xiaomi.sensor.back_cct", false, value));
    assert(!sheng::RejectInvalidFrontCct(cct, 33171089, name, false, value));
    assert(!sheng::RejectInvalidFrontCct(5, 5, "android.sensor.light", false, value));
  }
  for (float value : {1.0f, 131.6f, 4562.0f, 6382.0f, 15000.0f}) {
    assert(!sheng::RejectInvalidFrontCct(cct, cct, name, false, value));
  }
}
'''
with tempfile.TemporaryDirectory(prefix='sheng-front-cct-') as directory:
    source, binary = Path(directory) / 'cct.cpp', Path(directory) / 'cct'
    source.write_text(fixture)
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-I', str(root / 'aidl/sensors'),
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('Front-CCT validity, identity and metadata isolation passed under ASan/UBSan')

#!/usr/bin/env python3
"""Patch source-built display services and sheng's orientation event adapter."""
from pathlib import Path
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
display = rom / 'hardware/qcom-caf/sm8550/display'

wait = '''  // The stock KGSL driver probes asynchronously. Do not let the prebuilt
  // gralloc utility cache missing GPU alignment support for this process.
  int gpu_wait_attempts = 0;
  while (access("/dev/kgsl-3d0", F_OK) != 0 && gpu_wait_attempts++ < 100) {
    usleep(100000);
  }
  if (access("/dev/kgsl-3d0", F_OK) != 0) {
    ALOGE("KGSL unavailable after 10 seconds; retrying graphics service startup");
    return -ENODEV;
  }

'''
for relative in ('gralloc/service.cpp', 'composer/service.cpp'):
    source = display / relative
    content = source.read_text()
    if wait not in content:
        anchor = 'int main(int, char **) {\n'
        assert content.count(anchor) == 1
        content = content.replace(anchor, anchor + wait)
        content = content.replace('#include <hidl/LegacySupport.h>\n',
                                  '#include <hidl/LegacySupport.h>\n#include <unistd.h>\n')
        source.write_text(content)

sensors = rom / 'hardware/xiaomi'
source = sensors / 'aidl/sensors/HalProxyCallback.cpp'
content = source.read_text()
correction = '''        // sheng's stock device-orientation algorithm uses portrait zero,
        // while its built-in display uses landscape zero. Adjust only this
        // discrete rotation event; do not rewrite calibrated motion samples.
        static const bool landscape_orientation =
                ::android::base::GetProperty("ro.product.vendor.device", "") == "sheng";
        if (landscape_orientation && sensor.type == V2_1::SensorType::DEVICE_ORIENTATION &&
            event.u.scalar >= 0 && event.u.scalar <= 3) {
            event.u.scalar = (static_cast<int>(event.u.scalar) + 3) % 4;
        }

'''
if correction not in content:
    anchor = '        const V2_1::SensorInfo& sensor = mCallback->getSensorInfo(event.sensorHandle);\n\n'
    assert content.count(anchor) == 1
    content = content.replace(anchor, anchor + correction)
    content = content.replace('#include <cinttypes>\n', '#include <cinttypes>\n#include <android-base/properties.h>\n')
    source.write_text(content)

for repo, files, name in (
    (display, ('gralloc/service.cpp', 'composer/service.cpp'), 'display-services-wait-for-kgsl.patch'),
    (sensors, ('aidl/sensors/HalProxyCallback.cpp',), 'sheng-device-orientation-offset.patch'),
):
    diff = subprocess.run(['git', '-C', str(repo), 'diff', '--', *files],
                          check=True, capture_output=True).stdout
    assert diff
    (workspace / 'patches' / name).write_bytes(diff)
print('Patched the two installed display service entrypoints and device-orientation events.')

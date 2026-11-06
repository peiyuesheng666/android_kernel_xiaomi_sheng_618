#!/usr/bin/env python3
"""Include sheng's actual AIDL V2 lights HAL, not the SM8750 implementation."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

WORK = Path(__file__).resolve().parents[1]
DEVICE = WORK / 'device/xiaomi/sheng'
ROM = Path('/root/sheng-lineage/lineage-24.0')
DUMP = ROM.parent / 'firmware-dump/extract-source'
inputs = (
    'vendor/bin/hw/vendor.qti.hardware.lights.service',
    'vendor/etc/init/vendor.qti.hardware.lights.service.rc',
    'vendor/etc/vintf/manifest/vendor.qti.hardware.lights.service.xml',
)
hal = ET.parse(DUMP / inputs[2]).find('hal')
assert hal.get('format') == 'aidl'
assert hal.findtext('name') == 'android.hardware.light'
assert hal.findtext('version') == '2'
assert hal.findtext('fqname') == 'ILights/default'
dynamic = subprocess.check_output(['readelf', '-d', str(DUMP / inputs[0])], text=True)
needed = re.findall(r'\(NEEDED\).*\[([^\]]+)\]', dynamic)
platform_libraries = {'libbase.so', 'liblog.so', 'libhardware.so', 'libbinder_ndk.so',
                      'android.hardware.light-V2-ndk.so', 'libc++.so', 'libc.so', 'libm.so', 'libdl.so'}
assert set(needed) <= platform_libraries, f'Unresolved private lights libraries: {needed}'
# The selected QTI platform policy already labels this exact stock executable.
policy = subprocess.check_output([
    'git', '--git-dir=' + str(ROM / '.repo/projects/device/qcom/sepolicy_vndr/sm8550.git'),
    'show', 'refs/remotes/github/lineage-24.0-caf-sm8550:generic/vendor/common/file_contexts'
], text=True)
assert r'/vendor/bin/hw/vendor\.qti\.hardware\.lights\.service' in policy
assert 'hal_light_default_exec' in policy
inventory = DEVICE / 'proprietary-files.txt'
lines = inventory.read_text().splitlines()
entries = {line.lstrip('-').split(';')[0].split('|')[0].split(':')[-1]: line
           for line in lines if line and not line.startswith('#')}
for relative in inputs:
    assert (DUMP / relative).is_file()
    entries.setdefault(relative, relative)
inventory.write_text('# Standalone sheng stock blob inventory, including native Dolby and lights.\n'
                     + '\n'.join(entries[key] for key in sorted(entries)) + '\n')
report = {'aidl': 'android.hardware.light.ILights/default', 'version': 2,
          'implementation': 'original sheng vendor binary',
          'inputs_sha256': {name: hashlib.sha256((DUMP / name).read_bytes()).hexdigest() for name in inputs},
          'needed_platform_libraries': needed,
          'existing_qti_policy_verified': True, 'android17_elf_validation': 'pending build',
          'hardware_runtime_validated': False,
          'omitted_stock_java_library_xml': 'Refers to a legacy light-V2.0 Java jar; not required by the native AIDL HAL'}
(WORK / 'reports/lights-integration.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

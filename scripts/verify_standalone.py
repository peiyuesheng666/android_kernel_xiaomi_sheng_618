#!/usr/bin/env python3
"""Check standalone references and evaluate board settings without other device trees.

This is a scoped GNU make check, not a replacement for Android Soong/Kati.
"""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

WORK = Path(__file__).resolve().parents[1]
DEVICE = WORK / 'device/xiaomi/sheng'
ROM = Path('/root/sheng-lineage/lineage-24.0')
checked = []
for file in DEVICE.rglob('*'):
    if not file.is_file() or file.suffix not in ('.mk', '.bp', '.py', '.prop', '.dependencies'):
        continue
    text = file.read_text()
    assert 'sm8550-common' not in text, f'Former device dependency in {file}'
    checked.append(str(file.relative_to(DEVICE)))
    if file.suffix == '.bp':
        for source in re.findall(r'\bsrc:\s*"([^"]+)"', text):
            assert (file.parent / source).is_file(), f'Unresolved Soong input {file}: {source}'
for file in (DEVICE / 'device.mk', DEVICE / 'BoardConfig.mk'):
    for local in re.findall(r'\$\((?:LOCAL_PATH|DEVICE_PATH)\)/([A-Za-z0-9_./-]+)', file.read_text()):
        assert (DEVICE / local).exists(), f'Unresolved local config: {local}'
board = (DEVICE / 'BoardConfig.mk').read_text()
excluded_includes = []
sanitized = []
for line in board.splitlines():
    if re.match(r'^include\s+', line):
        excluded_includes.append(line)
    else:
        sanitized.append(line)
stub = "to-upper = $(shell printf '%s' '$(1)' | tr '[:lower:]' '[:upper:]')\n"
stub += "to-lower = $(shell printf '%s' '$(1)' | tr '[:upper:]' '[:lower:]')\n"
expect = {
    'TARGET_ARCH': 'arm64', 'TARGET_BOARD_PLATFORM': 'kalama',
    'BOARD_BOOTIMAGE_PARTITION_SIZE': '100663296',
    'BOARD_SUPER_PARTITION_SIZE': '11811160064',
    'BOARD_QTI_DYNAMIC_PARTITIONS_SIZE': '11800674304',
    'BOARD_SUPER_PARTITION_GROUPS': 'qti_dynamic_partitions',
    'TARGET_KERNEL_CONFIG': 'gki_defconfig vendor/kalama_GKI.config',
    'TARGET_KERNEL_CONFIG_EXT': 'device/xiaomi/sheng/configs/kernel/sheng.config',
    'TARGET_RECOVERY_FSTAB': 'device/xiaomi/sheng/rootdir/etc/fstab.qcom',
    'TARGET_VENDOR_PROP': 'device/xiaomi/sheng/properties/vendor.prop',
    'BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE': 'erofs',
    'BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE': 'ext4',
}
assertions = ''
for variable, value in expect.items():
    assertions += f'ifneq ($({variable}),{value})\n$(error Unexpected {variable}: $({variable}))\nendif\n'
assertions += 'ifeq ($(filter wl2866d.ko,$(BOARD_VENDOR_KERNEL_MODULES_LOAD)),)\n$(error Board regulator is missing)\nendif\n'
text = stub + '\n'.join(sanitized) + '\n' + assertions + '\n.PHONY: check\ncheck:\n\t@:\n'
with tempfile.TemporaryDirectory(prefix='sheng-make-check-') as directory:
    makefile = Path(directory) / 'Makefile'
    makefile.write_text(text)
    subprocess.run(['make', '-f', str(makefile), 'check'], cwd=ROM, check=True)
for file in DEVICE.rglob('*.xml'):
    ET.parse(file)
for file in DEVICE.rglob('*.sh'):
    subprocess.run(['bash', '-n', str(file)], check=True)
manifest = ET.parse(WORK / 'manifests/sheng.xml')
assert all(project.get('path') != 'device/xiaomi/sm8550-common' for project in manifest.getroot())
assert not (ROM / 'vendor/xiaomi/sm8550-common').exists(), 'Legacy vendor tree is still in the live build'
assert not (ROM / 'device/xiaomi/sm8550-common').exists(), 'Legacy device tree is still in the live build'
report = {'standalone_reference_check_passed': True, 'checked_files': checked,
          'gnu_make_board_values_checked': expect,
          'external_includes_deferred_to_android_build': excluded_includes,
          'full_android_build_passed': False, 'hardware_boot_tested': False}
(WORK / 'reports/standalone-checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(f'Standalone reference, XML/shell and scoped GNU make checks passed ({len(checked)} files)')

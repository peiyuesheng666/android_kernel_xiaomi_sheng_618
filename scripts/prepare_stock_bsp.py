#!/usr/bin/env python3
"""Prepare the verified complete stock BSP with source-built GKI swap modules."""
import json
import contextlib
import io
from pathlib import Path
import re

work = Path(__file__).resolve().parents[1]
device = work / 'device/xiaomi/sheng'
hardware = Path('/root/sheng-lineage/firmware-dump/hardware')
audit = json.loads((work / 'reports/stock-bsp-module-abi.json').read_text())
assert audit['effective_mix_passed'] and not audit['errors'] and not audit['duplicate_exports']
names = audit['stock_modules']
assert len(names) == 417 and not {'zram.ko', 'zsmalloc.ko'} & set(names)
plan = {'schema': 1, 'strategy': 'stock-vendor-bsp-source-gki',
        'stock_firmware': 'OS3.0.303.0.WNXCNXM',
        'source_keep_modules': ['zsmalloc.ko', 'zram.ko'],
        'stock_modules_sha256': {name: audit['stock_inputs'][name]['sha256'] for name in names}}
(device / 'kernel/stock-modules/module-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
manifest = []
for name in names:
    stage = Path(audit['stock_inputs'][name]['path']).parent.name
    assert stage in ('vendor_boot', 'vendor_dlkm')
    manifest.append(f'{stage} {name}')
(device / 'configs/modules/stock-modules.list').write_text('\n'.join(manifest) + '\n')


def load_names(file):
    result = []
    for line in file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name = Path(line).name
        assert re.fullmatch(r'[A-Za-z0-9_-]+\.ko', name), line
        assert name in plan['stock_modules_sha256'] or name in plan['source_keep_modules'], f'Unprepared loaded module: {name}'
        if name not in result:
            result.append(name)
    return result


lists = {}
loaded = {}
for filename, source in (
    ('modules.load.first_stage', hardware / 'modules/vendor_boot/modules.load'),
    ('modules.load.recovery', hardware / 'modules/vendor_boot/modules.load.recovery'),
    ('modules.load.vendor_dlkm', hardware / 'modules/vendor_dlkm/modules.load'),
):
    selected = load_names(source)
    if filename == 'modules.load.vendor_dlkm':
        selected = [name for name in selected if name not in plan['source_keep_modules']]
    if filename == 'modules.load.recovery' and 'nt36532_touch.ko' not in selected:
        selected.append('nt36532_touch.ko')
    (device / 'configs/modules' / filename).write_text('\n'.join(selected) + '\n')
    lists[filename] = len(selected)
    loaded[filename] = selected

# Derive complete ramdisk sets from actual imported symbols. modinfo dependencies
# normalize '-' to '_', so filenames alone are not a reliable dependency lookup.
with contextlib.redirect_stdout(io.StringIO()):
    import audit_stock_module_closure as inventory
effective = {name: inventory.modules[name] for name in names}
rom = inventory.rom
kernel_out = rom / 'out/target/product/sheng/obj/KERNEL_OBJ'
release = (kernel_out / 'include/config/kernel.release').read_text().strip()
staging = rom / 'out/target/product/sheng/obj/PACKAGING/kernel_modules_intermediates/lib/modules' / release
for name in plan['source_keep_modules']:
    matches = list(staging.rglob(name))
    assert len(matches) == 1
    module = inventory.abi.Module(matches[0])
    effective[name] = {'imports': module.imports(), 'exports': module.exports()}
exports = {symbol: ('vmlinux', crc) for symbol, crc in inventory.core.items()}
for name, item in effective.items():
    for symbol, crc in item['exports'].items():
        assert symbol not in exports
        exports[symbol] = (name, crc)
dependencies = {}
for name, item in effective.items():
    dependencies[name] = set()
    for symbol, crc in item['imports'].items():
        assert symbol in exports and exports[symbol][1] == crc
        provider = exports[symbol][0]
        if provider not in ('vmlinux', name):
            dependencies[name].add(provider)


def closure(roots):
    queue, selected = list(roots), set()
    while queue:
        name = queue.pop()
        if name not in selected:
            selected.add(name)
            queue.extend(dependencies[name])
    return sorted(selected)


plan['boot_modules'] = closure(loaded['modules.load.first_stage'])
plan['recovery_modules'] = closure(loaded['modules.load.recovery'])
for filename, values in (('modules.list.boot', plan['boot_modules']),
                         ('modules.list.recovery', plan['recovery_modules'])):
    (device / 'configs/modules' / filename).write_text('\n'.join(values) + '\n')
    lists[filename] = len(values)
(device / 'kernel/stock-modules/module-plan.json').write_text(json.dumps(plan, indent=2) + '\n')

board = device / 'BoardConfig.mk'
text = board.read_text()
text = text.replace('TARGET_AUTO_COLLECT_KERNEL_MODULE_DEPS := true', 'TARGET_AUTO_COLLECT_KERNEL_MODULE_DEPS := false')
marker = '# Stock BSP selected by module-plan.json; the kernel core stays LineageOS.'
if marker not in text:
    replacement = (marker + '\nTARGET_KERNEL_EXT_MODULES := ../../../device/xiaomi/sheng/kernel/stock-modules\n'
                   'SYSTEM_KERNEL_MODULES := zsmalloc.ko zram.ko\n'
                   'BOARD_SYSTEM_KERNEL_MODULES_LOAD := zsmalloc.ko zram.ko\n\nBOOT_KERNEL_MODULES')
    text, count = re.subn(r'TARGET_KERNEL_EXT_MODULES := \\\n.*?\n\nBOOT_KERNEL_MODULES', replacement, text, count=1, flags=re.S)
    assert count == 1
    text = text.replace('TARGET_KERNEL_EXT_MODULES += ../../../device/xiaomi/sheng/kernel/stock-modules\n', '')
    text, count = re.subn(r'BOARD_VENDOR_KERNEL_MODULES_LOAD \+= \\\n.*?xiaomi_touch\.ko wl2866d\.ko wl2868c\.ko\n', '', text, count=1, flags=re.S)
    assert count == 1
    text = text.replace('BOOT_KERNEL_MODULES += nt36532_touch.ko\n', '')
    text = text.replace('BOARD_VENDOR_RAMDISK_RECOVERY_KERNEL_MODULES_LOAD += nt36532_touch.ko\n', '')
board.write_text(text)
text = board.read_text()
old_boot = 'BOOT_KERNEL_MODULES := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.load.recovery))'
previous_boot = 'BOOT_KERNEL_MODULES := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.list.boot))'
new_boot = 'BOOT_KERNEL_MODULES := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.list.recovery))'
assert any(value in text for value in (old_boot, previous_boot, new_boot))
text = text.replace(old_boot, new_boot).replace(previous_boot, new_boot)
if '\nRECOVERY_KERNEL_MODULES :=' not in text:
    text = text.replace(new_boot, new_boot + '\nRECOVERY_KERNEL_MODULES := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.list.recovery))\nBOARD_RECOVERY_KERNEL_MODULES_LOAD := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.load.recovery))')
board.write_text(text)
print(json.dumps({'stock_bsp_modules': len(names), 'source_gki_modules': plan['source_keep_modules'],
                  'stock_load_lists': lists, 'kernel_core': 'LineageOS 5.15.220'}, indent=2))

#!/usr/bin/env python3
"""Sync the targeted local bring-up edits to the separate WSL device tree."""
from pathlib import Path
import shutil

workspace = Path(__file__).resolve().parents[1]
local = workspace / 'device/xiaomi/sheng'
target = Path('/root/sheng-lineage/lineage-24.0/device/xiaomi/sheng')
files = (
    'device.mk',
    'rootdir/etc/init.sheng.rc',
    'rootdir/etc/vendor.qti.camera.provider-service_64.rc',
    'configs/idc/NVTCapacitiveTouchScreen.idc',
    'configs/touch/sheng-touch-report',
    'configs/audio/mixer_paths_kalama_mtp.xml',
    'configs/audio/resourcemanager_kalama_mtp.xml',
    'configs/audio/sku_kalama/audio_effects.xml',
    'configs/audio/sku_kalama/audio_policy_configuration.xml',
    'properties/vendor.prop',
    'properties/odm.prop',
    'sepolicy/vendor/hal_lineage_touch_default.te',
    'sepolicy/vendor/hal_sheng_dolby.te',
    'sepolicy/vendor/file_contexts',
    'overlay/FrameworkResOverlaySheng/res/values/tablet-mode.xml',
)
for relative in files:
    source = local / relative
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or source.read_bytes() != destination.read_bytes():
        shutil.copyfile(source, destination)
    assert source.read_bytes() == destination.read_bytes(), relative
print(f'Synced and byte-verified {len(files)} targeted source files.')

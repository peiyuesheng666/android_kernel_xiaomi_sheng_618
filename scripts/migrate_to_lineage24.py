#!/usr/bin/env python3
"""Switch this task's existing shallow repo checkout to LineageOS 24.0."""
import json
from pathlib import Path
import shutil

WORK = Path(__file__).resolve().parents[1]
ROOT = Path('/root/sheng-lineage')
old = ROOT / 'lineage-23.2'
new = ROOT / 'lineage-24.0'
assert old.resolve().parent == ROOT.resolve() and new.resolve().parent == ROOT.resolve()
if old.exists():
    assert not new.exists(), 'Refuse to merge two source directories'
    old.rename(new)
assert (new / '.repo/manifests.git').is_dir()
scripts = ('setup_rom_workspace.sh', 'sync_lineage.sh', 'install_rom_configuration.sh',
           'install_standalone_vendor.sh', 'build_lineage.sh', 'preflight_sheng.py',
           'prepare_sheng_stock.py', 'export_lineage.py', 'verify_module_guard.py',
           'verify_standalone.py', 'continue_after_sync.sh')
for name in scripts:
    file = WORK / 'scripts' / name
    text = file.read_text().replace('lineage-23.2', 'lineage-24.0').replace('lineage_sheng-bp4a', 'lineage_sheng-cp2a')
    file.write_text(text)
for relative in ('manifests/sheng.xml', 'device/xiaomi/sheng/lineage.dependencies',
                 'device/xiaomi/sheng/README.md', 'device/xiaomi/sheng/AndroidProducts.mk',
                 'device/xiaomi/sheng/docs/BRINGUP.md'):
    file = WORK / relative
    file.write_text(file.read_text().replace('lineage-23.2', 'lineage-24.0')
                    .replace('LineageOS 23.2', 'LineageOS 24.0').replace('bp4a', 'cp2a'))
shutil.copyfile(WORK / 'manifests/sheng.xml', new / '.repo/local_manifests/sheng.xml')
report = {'target': 'LineageOS 24.0', 'aosp_tag': 'android-17.0.0_r1',
          'lunch': 'lineage_sheng-cp2a-userdebug', 'source_path': str(new),
          'reused_existing_git_objects': True, 'old_checkout_deleted': False,
          'independent_device_tree_preserved': True, 'stock_firmware_cache_preserved': True,
          'official_sm8550_kernel_branch': 'lineage-24.0', 'observed_kernel_version': '5.15.220'}
(WORK / 'reports/lineage24-migration.json').write_text(json.dumps(report, indent=2) + '\n')
print(f'Checkout renamed to {new}; scripts/configuration now target 24.0 / cp2a')

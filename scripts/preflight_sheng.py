#!/usr/bin/env python3
"""Check real pre-build inputs; a pass is not a ROM compilation or boot test."""
import argparse
import ast
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

WORK = Path(__file__).resolve().parents[1]
ROOT = Path('/root/sheng-lineage')
ROM = ROOT / 'lineage-24.0'
DEVICE = WORK / 'device/xiaomi/sheng'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-synced', action='store_true')
    args = parser.parse_args()
    subprocess.run(['python3', str(WORK / 'scripts/verify_standalone.py')], check=True)
    subprocess.run(['python3', str(WORK / 'scripts/audit_prebuilt_apks.py'), '--require-clean'], check=True)
    checks, errors, pending = [], [], []

    # repo's JSON cache is perpetually stale when ~/.gitconfig is absent.
    # Populate it before Siso enters its read-only source/home filesystem view.
    user_config = Path.home() / '.gitconfig'
    if not user_config.exists():
        try:
            user_config.touch(exist_ok=False)
        except FileExistsError:
            pass
    assert user_config.is_file()
    with (ROOT / 'logs/manifest-preflight.log').open('w') as output:
        subprocess.run(['python3', '.repo/repo/repo', 'manifest', '-r', '-o',
                        str(ROOT / 'logs/source-manifest.xml')], cwd=ROM,
                       stdout=output, stderr=subprocess.STDOUT, check=True)
    checks.append({'check': 'Repo metadata cache prepared outside build sandbox', 'passed': True})

    def check(label, condition, missing_source=False):
        checks.append({'check': label, 'passed': bool(condition)})
        if not condition:
            (pending if missing_source and not args.require_synced else errors).append(label)

    for file in list((WORK / 'scripts').glob('*.py')) + list(DEVICE.rglob('*.py')):
        ast.parse(file.read_text(), filename=str(file))
    checks.append({'check': 'Python scripts parse', 'passed': True})
    for file in (WORK / 'scripts').glob('*.sh'):
        subprocess.run(['bash', '-n', str(file)], check=True)
    checks.append({'check': 'Shell scripts parse', 'passed': True})
    for file in list(DEVICE.rglob('AndroidManifest.xml')) + list((DEVICE / 'overlay').rglob('config.xml')) + list((DEVICE / 'configs/vintf').glob('*.xml')):
        ET.parse(file)
    checks.append({'check': 'Device XML parses', 'passed': True})
    stock_props = {}
    for line in (ROOT / 'firmware-dump/partitions/odm/etc/build.prop').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            stock_props[key] = value
    product_text = (DEVICE / 'lineage_sheng.mk').read_text()
    for variable, expected in (('PRODUCT_DEVICE', stock_props['ro.product.odm.device']),
                               ('PRODUCT_MODEL', stock_props['ro.product.odm.model'])):
        match = re.search(r'^' + variable + r'\s*:=\s*(.+)$', product_text, re.M)
        check(variable + ' matches supplied stock ODM', match and match[1].strip() == expected)
    tablet_text = (DEVICE / 'device.mk').read_text()
    for file in DEVICE.rglob('*'):
        if file.is_file() and file.suffix in ('.mk', '.bp', '.py', '.prop', '.dependencies'):
            check('No common device reference: ' + str(file.relative_to(DEVICE)), 'sm8550-common' not in file.read_text())
    for excluded in ('XiaomiEsimSwitcher', 'android.hardware.consumerir.xml', 'android.hardware.location.gps.xml',
                     'android.hardware.nfc.xml', 'uinput-goodix.kl', 'CarrierConfigOverlayCommon', 'TelephonyOverlayCommon'):
        check('Phone entry removed: ' + excluded, excluded not in tablet_text)
    for name in ('novatek_nt36532_n81a_fw_csot.bin', 'novatek_nt36532_n81a_mp_csot.bin', 'n81a_nova_thp_config.ini'):
        check('Recovery touch firmware: ' + name, (ROM / 'vendor/xiaomi/sheng/proprietary/odm/firmware' / name).is_file())
    for category, name in (('idc', 'Vendor_0022_Product_5081.idc'), ('keychars', 'Vendor_0022_Product_5081.kcm')):
        check('Stock pen input: ' + name, (ROM / 'vendor/xiaomi/sheng/proprietary/system_ext/usr' / category / name).is_file())
    check('Local stock hardware inventory exists', (ROOT / 'firmware-dump/hardware/stock-hardware-inventory.json').is_file())
    for name in ('dolby-integration.json', 'lights-integration.json'):
        integration = json.loads((WORK / 'reports' / name).read_text())
        inputs = integration.get('stock_inputs', integration.get('inputs_sha256', {}))
        for relative in inputs:
            check('Integrated native input: ' + relative,
                  (ROM / 'vendor/xiaomi/sheng/proprietary' / relative).is_file())
    lights = ET.parse(ROM / 'vendor/xiaomi/sheng/proprietary/vendor/etc/vintf/manifest/vendor.qti.hardware.lights.service.xml').find('hal')
    check('Actual stock lights AIDL V2 included',
          lights.get('format') == 'aidl' and lights.findtext('version') == '2'
          and lights.findtext('fqname') == 'ILights/default')
    for repo in ('hardware/xiaomi', 'kernel/xiaomi/sm8550',
                 'kernel/xiaomi/sm8550-modules', 'kernel/xiaomi/sm8550-devicetrees'):
        check('Official dependency: ' + repo, (ROM / repo / '.git').exists(), True)
    for name in ('Android.bp', 'BoardConfigVendor.mk', 'sheng-vendor.mk'):
        check('Generated sheng vendor ' + name, (ROM / 'vendor/xiaomi/sheng' / name).is_file())
    for file in [ROM / 'vendor/xiaomi/sheng/Android.bp']:
        names = re.findall(r'^\s*name:\s*"([^"]+)"', file.read_text(), re.M)
        duplicates = [n for n, count in Counter(names).items() if count > 1]
        check(str(file.relative_to(ROM)) + ' has unique module names', not duplicates)
        if duplicates:
            errors.append('Duplicate module names: ' + ', '.join(duplicates[:12]))
    for file in ('dtb/stock.dtb', 'dtbo.img'):
        check('Stock sheng ' + file, (ROM / 'device/xiaomi/sheng-kernel' / file).is_file())
    spec = importlib.util.spec_from_file_location('sheng_module_abi', DEVICE / 'kernel/stock-modules/stage.py')
    abi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(abi)
    modules = list((ROM / 'device/xiaomi/sheng-kernel/stock-modules').glob('*.ko'))
    prepared = json.loads((WORK / 'reports/sheng-stock-preparation.json').read_text())['prepared_module_names']
    check('All prepared board modules present', sorted(p.name for p in modules) == prepared)
    for path in modules:
        parsed = abi.Module(path).imports()
        external = subprocess.check_output(['modprobe', '--dump-modversions', str(path)], text=True)
        expected = {line.split()[1]: int(line.split()[0], 16) for line in external.splitlines() if line.strip()}
        check('ELF CRC parser agrees with kmod: ' + path.name, parsed == expected)
    swap_bytes = sum(int(line.split()[2]) * 1024 for line in Path('/proc/swaps').read_text().splitlines()[1:])
    check('About 80 GiB swap active', swap_bytes >= 79 * 1024**3)
    check('Host build dependencies installed', (ROOT / 'logs/installed-packages.tsv').is_file())
    free = shutil.disk_usage('/mnt/c').free
    check('C: safety margin above 25 GiB', free >= 25 * 1024**3)
    report = {'preparation_checks_passed': not errors, 'device_dependencies_present': not pending,
              'full_platform_sync_complete': (ROOT / 'logs/rom-status.txt').read_text().strip() == 'synced',
              'rom_compiled': False, 'hardware_boot_tested': False,
              'c_free_gib': round(free / 1024**3, 2), 'checks': checks,
              'errors': errors, 'awaiting_sync': pending,
              'abi_validation_against_built_kernel': 'pending actual kernel build'}
    (WORK / 'reports/lineage-preflight.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'checks'}, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

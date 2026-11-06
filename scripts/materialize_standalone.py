#!/usr/bin/env python3
"""One-time migration of the existing sheng draft to a standalone device tree.

The authorized official LineageOS platform helpers retain their licenses.
No piano implementation is copied. This migration is not a build dependency.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

WORK = Path(__file__).resolve().parents[1]
DEVICE = WORK / 'device/xiaomi/sheng'
REF = Path('/root/sheng-612/reference/lineage-common')
ROOT = Path('/root/sheng-lineage')
receipt = []


def copy(relative, destination):
    source = REF / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    receipt.append({'source': relative, 'destination': str(destination.relative_to(DEVICE)),
                    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})


def assignments(text):
    """Return logical makefile statements without interpreting make expressions."""
    result = []
    current = ''
    for line in text.splitlines(keepends=True):
        current += line
        if not line.rstrip().endswith('\\'):
            result.append(current)
            current = ''
    if current:
        result.append(current)
    return result


def main():
    stamp = WORK / 'reports/standalone-migration.json'
    assert not stamp.exists(), 'Migration already applied; edit the independent tree directly'
    original_board = (DEVICE / 'BoardConfig.mk').read_text()
    original_device = (DEVICE / 'device.mk').read_text()

    # Board settings become a single local file. Platform settings are explicit;
    # the sheng measurements/config overrides replace the former phone defaults.
    own = []
    replaced = set()
    for block in assignments(original_board):
        if block.startswith('include device/xiaomi/'):
            continue
        if 'filter-out device/xiaomi/' in block:
            variable = block.split(':=', 1)[0].strip()
            partition = variable.removeprefix('TARGET_').removesuffix('_PROP').lower()
            block = f'{variable} := $(DEVICE_PATH)/properties/{partition}.prop\n'
        match = re.match(r'([A-Z_0-9]+)\s*:=', block)
        if match:
            replaced.add(match[1])
        own.append(block)
    base = []
    for block in assignments((REF / 'BoardConfigCommon.mk').read_text()):
        match = re.match(r'([A-Z_0-9]+)\s*[:+?]?=', block)
        if match and match[1] in replaced | {'COMMON_PATH'}:
            continue
        if 'vendor/xiaomi/sm8550-common' in block or 'SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS' in block:
            continue
        base.append(block)
    board = 'DEVICE_PATH := device/xiaomi/sheng\n\n' + ''.join(base) + '\n' + ''.join(own)
    board = board.replace('$(COMMON_PATH)', '$(DEVICE_PATH)')
    board = board.replace('device/xiaomi/sm8550-common', 'device/xiaomi/sheng')
    board = board.replace('/modules.load.', '/configs/modules/modules.load.')
    board = board.replace('XIAOMI_SSI_PARTITIONS', 'SHENG_SYSTEM_PARTITIONS')
    board = board.replace('XIAOMI_TREBLE_PARTITIONS', 'SHENG_VENDOR_PARTITIONS')
    board = board.replace('BOARD_XIAOMI_DYNAMIC_PARTITIONS', 'BOARD_QTI_DYNAMIC_PARTITIONS')
    board = board.replace('xiaomi_dynamic_partitions', 'qti_dynamic_partitions')
    board = board.replace('$(DEVICE_PATH)/init/fstab.qcom', '$(DEVICE_PATH)/rootdir/etc/fstab.qcom')
    board = re.sub(r'\n\s*nxp/opensource/driver\n', '\n', board)
    # Drop the private-policy root: it only contained the absent eSIM app.
    board = board.replace('BOARD_VENDOR_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy/vendor\n', '', 1)
    (DEVICE / 'BoardConfig.mk').write_text(board)

    # Flatten the already audited tablet product. There is no common product
    # include and only one vendor output namespace.
    platform = (DEVICE / 'platform/common-tablet.mk').read_text()
    platform = platform.replace('device/xiaomi/sm8550-common', 'device/xiaomi/sheng')
    platform = platform.replace('vendor/xiaomi/sm8550-common/sm8550-common-vendor.mk',
                                'vendor/xiaomi/sheng/sheng-vendor.mk')
    platform = platform.replace('    libudfpshandler\n', '')
    platform = platform.replace('android.hardware.biometrics.fingerprint-service.xiaomi \\\n',
                                'android.hardware.biometrics.fingerprint-service.xiaomi\n')
    platform = platform.replace('$(LOCAL_PATH)/configs/audio/sku_kalama/', '$(LOCAL_PATH)/configs/audio/sku_kalama/')
    additions = '\n'.join(line for line in original_device.splitlines()
                           if 'inherit-product,' not in line and not line.startswith('# SPDX-'))
    product = platform + '\n# sheng board configuration\n' + additions + '\n'
    (DEVICE / 'device.mk').write_text(product)

    # Consolidate approved blob entries. Runtime extraction no longer reads any
    # other device manifest or emits a shared vendor namespace.
    entries = {}
    for file in (DEVICE / 'platform/proprietary-files.txt', DEVICE / 'proprietary-files.txt'):
        for line in file.read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                destination = line.lstrip('-').split(';')[0].split('|')[0].split(':')[-1]
                assert destination not in entries or entries[destination] == line
                entries[destination] = line
    (DEVICE / 'proprietary-files.txt').write_text(
        '# Stock sheng OS3.0.303.0.WNXCNXM, standalone approved blob inventory.\n'
        '# All sources are cached locally; missing input is an error.\n\n'
        + '\n'.join(entries[key] for key in sorted(entries)) + '\n')

    # Required local config files; existing stock-derived sheng files take
    # precedence over platform reference data.
    for relative in ('configs/config.fs', 'configs/sensors/hals.conf',
                     'configs/permissions/camerax-vendor-extensions.xml',
                     'configs/vintf/framework_manifest.xml'):
        copy(relative, DEVICE / relative)
    for source in (REF / 'configs/audio').rglob('*'):
        if source.is_file():
            relative = source.relative_to(REF).as_posix()
            target = DEVICE / relative
            if not target.exists():
                copy(relative, target)
    for stage in ('first_stage', 'vendor_dlkm', 'recovery'):
        copy(f'modules.load.{stage}', DEVICE / f'configs/modules/modules.load.{stage}')

    # Bring in the generic Qualcomm init helper sources explicitly, with their
    # original copyright notices. The independent fstab/init.sheng stay local.
    init_bp = (REF / 'init/Android.bp').read_text()
    init_bp = re.sub(r'prebuilt_etc \{\s*name: "fstab.qcom",.*?\n\}\n', '', init_bp, flags=re.S)
    for source in (REF / 'init').iterdir():
        if not source.is_file() or source.name in ('Android.bp', 'fstab.qcom'):
            continue
        category = 'bin' if source.suffix == '.sh' else 'etc'
        copy('init/' + source.name, DEVICE / 'rootdir' / category / source.name)
    init_bp = re.sub(r'src: "([^"]+)"', lambda m: 'src: "' +
                     ('bin/' if m[1].endswith('.sh') else 'etc/') + m[1] + '"', init_bp)
    (DEVICE / 'rootdir/Android.bp').write_text(init_bp)

    # Policy declarations and device paths become local. Retain the existing
    # sheng FPC rules; merge platform permissions under the same policy root.
    excluded = {'hal_nfc_default.te', 'nfc.te', 'hal_ir_default.te', 'hal_mlipay.te'}
    for source in (REF / 'sepolicy/vendor').iterdir():
        if source.name in excluded or not source.is_file():
            continue
        target = DEVICE / 'sepolicy/vendor' / source.name
        old = target.read_text() if target.exists() else ''
        copy('sepolicy/vendor/' + source.name, target)
        if old:
            target.write_text(target.read_text() + '\n# sheng board additions\n' + old)

    # Put framework defaults in the existing sheng RRO, excluding resources
    # already specified by sheng's own stock-derived overlay files.
    overlay = DEVICE / 'overlay/FrameworkResOverlaySheng/res/values'
    names = set()
    for xml in overlay.glob('*.xml'):
        names.update((e.tag, e.get('name')) for e in ET.parse(xml).getroot())
    defaults = ET.parse(REF / 'overlay/FrameworkResOverlayCommon/res/values/config.xml')
    for element in list(defaults.getroot()):
        if (element.tag, element.get('name')) in names:
            defaults.getroot().remove(element)
    ET.indent(defaults)
    defaults.write(overlay / 'platform-defaults.xml', encoding='utf-8', xml_declaration=True)
    rename = {'FrameworkResOverlayCommon': 'FrameworkResOverlaySheng',
              'SystemUIOverlayCommon': 'SystemUIResOverlaySheng',
              'SettingsOverlayCommon': 'SettingsResOverlaySheng',
              'WifiOverlayCommon': 'WifiResOverlaySheng',
              'LineageResXiaomi': 'LineageResOverlaySheng'}
    for old, new in rename.items():
        if old == 'FrameworkResOverlayCommon':
            continue
        for source in (REF / 'overlay' / old).rglob('*'):
            if source.is_file():
                relative = source.relative_to(REF).as_posix()
                target = DEVICE / 'overlay' / new / source.relative_to(REF / 'overlay' / old)
                copy(relative, target)
                if source.suffix in ('.bp', '.xml'):
                    text = target.read_text().replace(old, new).replace('vendor: true', 'device_specific: true')
                    if source.name == 'AndroidManifest.xml':
                        text = re.sub(r'package="([^"]+)"', lambda m: 'package="' + m[1] + '.sheng"', text, count=1)
                    target.write_text(text)
    product = (DEVICE / 'device.mk').read_text()
    for old, new in rename.items():
        product = product.replace(old, new)
    # The board RRO is declared once in the platform's overlay section.
    product = product.replace('    FrameworkResOverlaySheng init.sheng.rc', '    init.sheng.rc')
    (DEVICE / 'device.mk').write_text(product)

    root_bp = (DEVICE / 'Android.bp').read_text()
    symlinks = (REF / 'Android.bp').read_text()
    symlinks = re.sub(r'install_symlink \{\s*name: "rfs_msm_mpss_readonly_mbnconfig_symlink",.*?\n\}\n', '', symlinks, flags=re.S)
    for old in ('firmware_wlanmdsp.otaupdate_symlink', 'firmware_wlan_mac.bin_symlink', 'firmware_WCNSS_qcom_cfg.ini_symlink'):
        new = 'sheng_' + old
        symlinks = symlinks.replace(old, new)
        product = product.replace(old, new)
    (DEVICE / 'Android.bp').write_text(symlinks + '\n' + root_bp)
    (DEVICE / 'device.mk').write_text(product)

    # Preserve upstream fixups as local source with its SPDX notice; no dynamic
    # import of another device, and no second vendor output is created.
    source = (REF / 'extract-files.py').read_text().split('\nmodule = ExtractUtilsModule(', 1)[0]
    source = source.replace("'device/xiaomi/sm8550-common'", "'device/xiaomi/sheng'")
    prefix = '''#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools/extract-utils'))
'''
    source = '\n'.join(line for line in source.splitlines() if not line.startswith('#!'))
    source += '''
# The supplied sheng package has malformed XML declarations in these files.
blob_fixups.update({
    ('odm/etc/camera/enhance_motiontuning.xml',
     'odm/etc/camera/night_motiontuning.xml',
     'odm/etc/camera/motiontuning.xml'): blob_fixup()
        .regex_replace(r'<\\?xml=version=', '<?xml version='),
})
module = ExtractUtilsModule('sheng', 'xiaomi', blob_fixups=blob_fixups,
    lib_fixups=lib_fixups, namespace_imports=namespace_imports)
if __name__ == '__main__':
    ExtractUtils.device(module).run()
'''
    (DEVICE / 'extract-files.py').write_text(prefix + source)

    deps = [{'repository': name, 'target_path': path, 'branch': 'lineage-23.2'} for name, path in (
        ('android_hardware_xiaomi', 'hardware/xiaomi'),
        ('android_kernel_xiaomi_sm8550', 'kernel/xiaomi/sm8550'),
        ('android_kernel_xiaomi_sm8550-modules', 'kernel/xiaomi/sm8550-modules'),
        ('android_kernel_xiaomi_sm8550-devicetrees', 'kernel/xiaomi/sm8550-devicetrees'))]
    (DEVICE / 'lineage.dependencies').write_text(json.dumps(deps, indent=2) + '\n')
    manifest = ET.parse(WORK / 'manifests/sheng.xml')
    for project in list(manifest.getroot()):
        if project.get('path') == 'device/xiaomi/sm8550-common':
            manifest.getroot().remove(project)
    ET.indent(manifest)
    manifest.write(WORK / 'manifests/sheng.xml', encoding='utf-8', xml_declaration=True)

    # Historical generated files are archived for provenance, outside the live
    # device tree. Only exact, task-owned files are unlinked.
    archive = WORK / 'reports/history/pre-standalone'
    for name in ('common-tablet.mk', 'proprietary-files.txt'):
        old = DEVICE / 'platform' / name
        target = archive / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old, target)
        old.unlink()
    (DEVICE / 'platform').rmdir()
    stamp.write_text(json.dumps({'standalone': True, 'runtime_common_device_dependency': False,
        'piano_files_copied': 0, 'source_reference_commit': 'dfb9e56a0d9c38742ec569471d25657f91a4a38b',
        'licensed_platform_inputs': receipt, 'blob_entries': len(entries)}, indent=2) + '\n')
    print(f'Standalone tree materialized; {len(entries)} blob entries; {len(receipt)} licensed helper/config inputs')


if __name__ == '__main__':
    main()

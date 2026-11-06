#!/usr/bin/env python3
"""Refresh independently configured sheng inputs from the local stock cache."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

WORK = Path(__file__).resolve().parents[1]
DEVICE = WORK / 'device/xiaomi/sheng'
ROOT = Path('/root/sheng-lineage')
DUMP = ROOT / 'firmware-dump/partitions'
HARDWARE = ROOT / 'firmware-dump/hardware'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    report = {'source': 'OS3.0.303.0.WNXCNXM', 'standalone': True,
              'copied_configuration': [], 'board_modules': []}
    normalized = ROOT / 'firmware-dump/extract-source'
    normalized.mkdir(exist_ok=True)
    for partition in DUMP.iterdir():
        if partition.is_dir():
            target = partition / 'system' if partition.name == 'system' else partition
            link = normalized / partition.name
            if not link.exists():
                link.symlink_to(target, target_is_directory=True)
    entries = []
    missing = []
    for line in (DEVICE / 'proprietary-files.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        source = line.lstrip('-').split(';')[0].split('|')[0].split(':')[0]
        entries.append(source)
        if not (normalized / source).is_file():
            missing.append(source)
    assert not missing, f'Missing cached proprietary inputs: {missing}'
    report['device_blob_count'] = len(entries)

    for source, destination in (
        ('vendor/etc/audio/sku_kalama/mixer_paths_kalama_mtp.xml', 'configs/audio/mixer_paths_kalama_mtp.xml'),
        ('vendor/etc/audio/sku_kalama/resourcemanager_kalama_mtp.xml', 'configs/audio/resourcemanager_kalama_mtp.xml'),
        ('vendor/etc/card-defs.xml', 'configs/audio/card-defs.xml'),
        ('vendor/etc/microphone_characteristics.xml', 'configs/audio/microphone_characteristics.xml'),
        ('system/usr/idc/uinput-fpc.idc', 'configs/idc/uinput-fpc.idc'),
        ('system/usr/keylayout/uinput-fpc.kl', 'configs/keylayout/uinput-fpc.kl'),
    ):
        target = DEVICE / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(normalized / source, target)
        report['copied_configuration'].append({'source': source, 'target': destination, 'sha256': digest(target)})
    kernel = ROOT / 'lineage-24.0/device/xiaomi/sheng-kernel'
    (kernel / 'dtb').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HARDWARE / 'boot-components/stock.dtb', kernel / 'dtb/stock.dtb')
    shutil.copyfile(HARDWARE / 'boot-images/dtbo.img', kernel / 'dtbo.img')
    report['stock_dt'] = {name: digest(kernel / name) for name in ('dtb/stock.dtb', 'dtbo.img')}

    spec = importlib.util.spec_from_file_location('sheng_abi', DEVICE / 'kernel/stock-modules/stage.py')
    abi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(abi)
    stock = kernel / 'stock-modules'
    stock.mkdir(exist_ok=True)
    selected = []
    for line in (DEVICE / 'configs/modules/stock-modules.list').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        stage, filename = line.split()
        assert stage in ('vendor_boot', 'vendor_dlkm') and filename.endswith('.ko') and '/' not in filename
        source = HARDWARE / 'modules' / stage / filename
        target = stock / filename
        shutil.copyfile(source, target)
        module = abi.Module(target)
        report['board_modules'].append({'file': filename, 'source_stage': stage, **module.info,
                                       'sha256': digest(target)})
        selected.append(filename)
    report['prepared_module_names'] = sorted(selected)
    assert sorted(p.name for p in stock.glob('*.ko')) == sorted(selected), 'Unexpected stale stock module'
    (WORK / 'reports/sheng-stock-preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Independent stock inputs ready: {len(entries)} blobs, {len(selected)} board modules')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Cache stock hardware inputs read-only from the supplied fastboot package."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

WORK = Path(__file__).resolve().parents[1]
ROOT = Path('/root/sheng-lineage/firmware-dump')
SOURCE = Path(json.loads((WORK / 'reports/stock-boot.json').read_text())['boot']['input']).parent


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for data in iter(lambda: file.read(8 * 1024**2), b''):
            digest.update(data)
    return digest.hexdigest()


def cache(source, destination):
    assert not destination.resolve().is_relative_to(SOURCE.parent.resolve())
    before = source.stat()
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = sha(source)
    if destination.exists():
        assert sha(destination) == expected, f'Existing cached copy differs: {destination}'
    else:
        with source.open('rb') as src, destination.open('xb') as dst:
            shutil.copyfileobj(src, dst, 8 * 1024**2)
        assert sha(destination) == expected, f'Copy verification failed: {destination}'
    after = source.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    return {'source': str(source), 'cached': str(destination), 'bytes': before.st_size, 'sha256': expected}


def main():
    hardware = ROOT / 'hardware'
    metadata = hardware / 'metadata'
    metadata.mkdir(parents=True, exist_ok=True)
    flash = (SOURCE.parent / 'flash_all.bat').read_text(errors='replace')
    (metadata / 'flash_all.bat.source.txt').write_text(flash)
    boot_partitions = {'boot', 'vendor_boot', 'init_boot', 'recovery', 'dtbo', 'vbmeta', 'vbmeta_system'}
    firmware_partitions = {'abl', 'xbl', 'xbl_config', 'shrm', 'aop', 'aop_config', 'tz', 'devcfg',
                           'featenabler', 'hyp', 'uefi', 'uefisecapp', 'modem', 'bluetooth', 'dsp',
                           'keymaster', 'qupfw', 'cpucp', 'xbl_ramdump', 'imagefv'}
    report = {'source_package': str(SOURCE.parent), 'original_package_write_operations': 0,
              'images': [], 'kernel_modules': [], 'partition_files': []}
    for partition, filename in re.findall(r'flash\s+([a-z0-9_]+)\s+%~dp0images/([^\s]+)', flash):
        partition = partition.removesuffix('_ab')
        if partition not in boot_partitions | firmware_partitions:
            continue
        group = 'boot-images' if partition in boot_partitions else 'firmware-images'
        item = cache(SOURCE / filename, hardware / group / (partition + '.img'))
        item['partition'] = partition
        report['images'].append(item)
        print(f'Cached and verified {partition}: {item["bytes"]:,} bytes', flush=True)
    for file in SOURCE.glob('*.xml'):
        cache(file, metadata / file.name)
    components = hardware / 'boot-components'
    components.mkdir(exist_ok=True)
    for source, name in (
        (Path('/root/sheng-612/stock/vendor_boot/dtb'), 'stock.dtb'),
        (Path('/root/sheng-612/stock/vendor_boot/bootconfig'), 'bootconfig'),
        (Path('/root/sheng-612/stock/vendor_boot-files/first_stage_ramdisk/fstab.qcom'), 'fstab.qcom'),
    ):
        cache(source, components / name)
    spec = importlib.util.spec_from_file_location('sheng_abi', WORK / 'device/xiaomi/sheng/kernel/stock-modules/stage.py')
    abi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(abi)
    module_roots = {
        'vendor_boot': Path('/root/sheng-612/stock/vendor_boot-files/lib/modules'),
        'vendor_dlkm': ROOT / 'partitions/vendor_dlkm/lib/modules',
        'system_dlkm': ROOT / 'partitions/system_dlkm/lib/modules',
    }
    for stage, directory in module_roots.items():
        target = hardware / 'modules' / stage
        target.mkdir(parents=True, exist_ok=True)
        for file in sorted(directory.glob('*')):
            if not file.is_file() or file.is_symlink():
                continue
            cached = target / file.name
            if not cached.exists():
                shutil.copyfile(file, cached)
            digest = sha(cached)
            assert digest == sha(file)
            if file.suffix == '.ko':
                module = abi.Module(cached)
                report['kernel_modules'].append({'stage': stage, 'file': file.name,
                    'name': module.info.get('name'), 'vermagic': module.info.get('vermagic'),
                    'depends': module.info.get('depends'), 'sha256': digest})
    for partition in ('vendor', 'odm', 'vendor_dlkm', 'system_dlkm'):
        directory = ROOT / 'partitions' / partition
        for file in sorted(directory.rglob('*')):
            if file.is_symlink():
                report['partition_files'].append({'path': str(file.relative_to(ROOT)), 'symlink': str(file.readlink())})
            elif file.is_file():
                report['partition_files'].append({'path': str(file.relative_to(ROOT)),
                    'bytes': file.stat().st_size, 'sha256': sha(file)})
    manifest = hardware / 'stock-hardware-inventory.json'
    manifest.write_text(json.dumps(report, indent=2) + '\n')
    summary = {'source_package': report['source_package'], 'original_package_write_operations': 0,
               'images': report['images'], 'module_files': len(report['kernel_modules']),
               'unique_module_names': len({m['name'] for m in report['kernel_modules']}),
               'module_stages': {s: sum(m['stage'] == s for m in report['kernel_modules']) for s in module_roots},
               'partition_inventory_entries': len(report['partition_files']),
               'inventory': str(manifest), 'inventory_sha256': sha(manifest)}
    (WORK / 'reports/stock-hardware-cache.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'images'}, indent=2))


if __name__ == '__main__':
    main()

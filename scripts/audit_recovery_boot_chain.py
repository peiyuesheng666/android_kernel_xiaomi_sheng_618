#!/usr/bin/env python3
"""Inspect actual stock/released boot containers and their merged newc archives."""
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
stock = Path('/root/sheng-lineage/firmware-dump/hardware/boot-images')
released = work / 'artifacts/lineage-24.0-20261105-UNOFFICIAL-sheng'
output = Path('/root/sheng-lineage/recovery-debug')
output.mkdir(exist_ok=True)


def cpio(path):
    raw = subprocess.run(['lz4', '-dc', str(path)], check=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    entries = {}
    offset = 0
    while offset + 110 <= len(raw):
        if raw[offset:offset + 6] not in (b'070701', b'070702'):
            assert not raw[offset:].strip(b'\0'), (str(path), offset)
            break
        fields = [int(raw[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        name = raw[offset + 110:offset + 110 + namesize - 1].decode()
        offset = (offset + 110 + namesize + 3) & ~3
        data = raw[offset:offset + size]
        offset = (offset + size + 3) & ~3
        if name == 'TRAILER!!!':
            continue
        entries[name.removeprefix('./')] = (mode, data)
    return entries


def summarize(entries):
    modules = {Path(name).name: data for name, (mode, data) in entries.items()
               if name.startswith('lib/modules/') and name.endswith('.ko')}
    normalized = {name.removesuffix('.ko').replace('-', '_') for name in modules}
    lists = {}
    for name, (mode, data) in entries.items():
        if name.startswith('lib/modules/') and Path(name).name.startswith('modules.load'):
            lines = [line.strip() for line in data.decode().splitlines()
                     if line.strip() and not line.startswith('#')]
            lists[name] = {'count': len(lines),
                           'missing_modules': [line for line in lines
                                               if Path(line).name.removesuffix('.ko').replace('-', '_') not in normalized]}
    important = {}
    for name in ('init', 'init.recovery.qcom.rc', 'system/etc/init/init.recovery.qcom.rc',
                 'system/etc/init/hw/init.rc', 'system/etc/recovery.fstab', 'fstab.qcom',
                 'system/bin/init', 'system/bin/recovery'):
        if name in entries:
            mode, data = entries[name]
            important[name] = {'mode': oct(mode), 'bytes': len(data),
                               'sha256': hashlib.sha256(data).hexdigest()}
            if stat.S_ISLNK(mode) or name.endswith('.rc'):
                important[name]['content'] = data.decode(errors='replace')
    return {'module_count': len(modules), 'load_lists': lists, 'important': important,
            'module_hashes': {n: hashlib.sha256(d).hexdigest() for n, d in modules.items()}}


report = {'images': {}, 'merged': {}}
archives = {}
for label, folder in (('stock', stock), ('released', released)):
    archives[label] = {}
    for name in ('boot', 'vendor_boot', 'init_boot', 'recovery'):
        target = output / label / name
        target.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([sys.executable, str(rom / 'system/tools/mkbootimg/unpack_bootimg.py'),
                                 '--boot_img', str(folder / (name + '.img')),
                                 '--out', str(target)], check=True, capture_output=True, text=True)
        report['images'][f'{label}/{name}'] = {'header': result.stdout}
        merged = {}
        ramdisks = sorted(target.glob('vendor_ramdisk[0-9]*')) if name == 'vendor_boot' else [target / 'ramdisk']
        for file in ramdisks:
            if file.is_file() and file.stat().st_size:
                merged.update(cpio(file))
        archives[label][name] = merged
        report['images'][f'{label}/{name}']['ramdisk'] = summarize(merged)
for label in archives:
    for vendor_label in archives:
        # A/B recovery ramdisk is prepended; vendor and generic archives follow.
        merged = archives[label]['recovery'] | archives[vendor_label]['vendor_boot'] | archives[vendor_label]['init_boot']
        report['merged'][f'{label}-recovery+{vendor_label}-vendor_boot+init_boot'] = summarize(merged)
(work / 'reports/recovery-boot-chain.json').write_text(json.dumps(report, indent=2) + '\n')
for name, data in report['images'].items():
    print(name, data['header'].splitlines()[:5], 'modules:', data['ramdisk']['module_count'])
for name, data in report['merged'].items():
    print(name, json.dumps({k: {'count': v['count'], 'missing_count': len(v['missing_modules']),
                               'missing_first_8': v['missing_modules'][:8]}
                            for k, v in data['load_lists'].items()}))

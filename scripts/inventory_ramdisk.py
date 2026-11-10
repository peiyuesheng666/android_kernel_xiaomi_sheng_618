#!/usr/bin/env python3
"""Inspect newc archives and preserve regular driver/config files, no symlinks."""
import gzip
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess

WORK = Path('/root/sheng-source-inputs')
REPORTS = Path(__file__).resolve().parents[1] / 'reports'
stock_report = json.loads((REPORTS / 'stock-boot.json').read_text())
stock_release = next(s.split()[2] for s in stock_report['kernel']['banners'] if re.match(r'Linux version \d', s))

def unpack(path):
    data = path.read_bytes()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    elif data[:4] in (b'\x02\x21\x4c\x18', b'\x04\x22\x4d\x18'):
        data = subprocess.run(['lz4', '-dc', str(path)], capture_output=True, check=True).stdout
    offset = 0
    entries = []
    root = WORK / 'stock' / (path.parent.name + '-files')
    while offset < len(data):
        if data[offset:offset+6] not in (b'070701', b'070702'):
            if not any(data[offset:]):
                break
            raise ValueError(f'Unsupported cpio magic at {offset}: {path}')
        fields = [int(data[offset+6+i*8:offset+14+i*8], 16) for i in range(13)]
        mode, size, name_size = fields[1], fields[6], fields[11]
        name_start = offset + 110
        name = data[name_start:name_start+name_size-1].decode()
        body = (name_start + name_size + 3) & ~3
        end = body + size
        if end > len(data):
            raise ValueError('Truncated cpio')
        offset = (end + 3) & ~3
        if name == 'TRAILER!!!':
            break
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'Unsafe cpio path: {name}')
        entry = {'path': name, 'mode': oct(mode), 'bytes': size}
        if stat.S_ISREG(mode):
            output = root.joinpath(*relative.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data[body:end])
            if name.endswith('.ko'):
                result = subprocess.run(['modinfo', '-k', stock_release, '-F', 'vermagic', str(output)], capture_output=True, text=True)
                entry['vermagic'] = result.stdout.strip()
        elif stat.S_ISLNK(mode):
            entry['link_target'] = data[body:end].decode(errors='replace')
        entries.append(entry)
    return entries

results = {}
for sub in ('vendor_boot', 'init_boot'):
    for path in (WORK / 'stock' / sub).glob('*ramdisk*'):
        if path.is_file():
            entries = unpack(path)
            results[str(path)] = entries
            modules = [e for e in entries if e['path'].endswith('.ko')]
            print(f'{sub}: {len(entries)} entries, {len(modules)} modules')
            print('vermagic:', sorted({e.get('vermagic') for e in modules}))
            print('module configs:', [e['path'] for e in entries if 'modules.' in e['path']])
blob = (WORK / 'stock/vendor_boot/dtb').read_bytes()
offset = 0
dtbs = []
while offset < len(blob):
    if blob[offset:offset+4] != b'\xd0\x0d\xfe\xed':
        if not any(blob[offset:]):
            break
        raise ValueError(f'Unexpected DTB trailer at {offset}')
    size = struct.unpack_from('>I', blob, offset+4)[0]
    if size < 40 or offset+size > len(blob):
        raise ValueError('Invalid DTB size')
    path = WORK / 'stock/vendor_boot' / f'dtb-{len(dtbs):02d}.dtb'
    path.write_bytes(blob[offset:offset+size])
    result = subprocess.run(['dtc', '-q', '-I', 'dtb', '-O', 'dts', str(path)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    path.with_suffix('.dts').write_text(result.stdout)
    compatibles = re.findall(r'compatible = ([^;]+);', result.stdout)
    dtbs.append({'index': len(dtbs), 'offset': offset, 'bytes': size,
                 'root_compatible': compatibles[0] if compatibles else None})
    offset += size
results['device_trees'] = dtbs
print('Stock base DTBs:', dtbs)
REPORTS.mkdir(exist_ok=True)
(REPORTS / 'stock-ramdisk.json').write_text(json.dumps(results, indent=2), encoding='utf-8')

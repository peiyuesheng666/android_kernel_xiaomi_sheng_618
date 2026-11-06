#!/usr/bin/env python3
"""Find actual old C ABI imports that the official Lineage shim implements."""
import json
from pathlib import Path
import struct

work = Path(__file__).resolve().parents[1]
root = Path('/root/sheng-lineage/lineage-24.0/vendor/xiaomi/sheng/proprietary')
targets, checked = [], 0
for file in root.rglob('*'):
    if not file.is_file():
        continue
    with file.open('rb') as stream:
        header = stream.read(64)
    if len(header) < 64 or header[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', header, 18)[0] != 183:
        continue
    data = file.read_bytes()
    shoff = struct.unpack_from('<Q', data, 40)[0]
    entry_size, count, names_index = struct.unpack_from('<HHH', data, 58)
    assert entry_size == 64 and shoff + count * 64 <= len(data)
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + n * 64) for n in range(count)]
    def section(s):
        return data[s[4]:s[4] + s[5]]
    def string(blob, offset):
        return blob[offset:blob.index(b'\0', offset)].decode()
    names = section(sections[names_index])
    symbols = next((s for s in sections if string(names, s[0]) == '.dynsym'), None)
    if symbols is None:
        continue
    checked += 1
    table, strings = section(symbols), section(sections[symbols[6]])
    imports = []
    assert symbols[9] == 24
    for offset in range(0, len(table), 24):
        name, info, _, index, _, _ = struct.unpack_from('<IBBHQQ', table, offset)
        if index == 0 and info >> 4 in (1, 2):
            symbol = string(strings, name)
            if symbol in ('SetTaskProfiles', 'CgroupGetControllerPath'):
                imports.append(symbol)
    if imports:
        targets.append({'path': str(file.relative_to(root)), 'symbols': sorted(imports)})
report = {'aarch64_dynamic_elfs_checked': checked, 'targets': sorted(targets, key=lambda row: row['path']),
          'shim': 'libprocessgroup_shim.so', 'implementation': 'official hardware/lineage/compat/libprocessgroup'}
(work / 'reports/processgroup-compat-audit.json').write_text(json.dumps(report, indent=2) + '\n')
(work / 'device/xiaomi/sheng/processgroup-compat.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

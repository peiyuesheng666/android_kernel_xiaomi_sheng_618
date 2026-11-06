#!/usr/bin/env python3
"""Correct four audited OEM allocations for this build's GraphicBuffer ABI."""
from pathlib import Path
import hashlib
import json
import re
import struct

workspace = Path(__file__).resolve().parents[1]
source = Path('/root/sheng-lineage/firmware-dump/partitions/odm/lib64/hw/camera.xiaomi.so')
original = source.read_bytes()
original_hash = '845202770a4171c0a65538716c1fcb976923efe390ef7bf92c79dbbac7a326dd'
assert hashlib.sha256(original).hexdigest() == original_hash
assert original[:5] == b'\x7fELF\x02'
measurement = (workspace / 'reports/device/system-bringup-r2-followup-20261106/graphicbuffer-size-check.txt').read_text()
measurement = re.sub(r'\x1b\[[0-9;]*m', '', measurement)
assert "expression evaluates to '3376 == 256'" in measurement
size = 3376
old_instruction = 0x52802000  # mov w0, #256
new_instruction = 0x52800000 | (size << 5)  # mov w0, #3376
addresses = (0xe6ab0, 0xe6fe4, 0xe73e8, 0xe74b0)
ph_offset = struct.unpack_from('<Q', original, 32)[0]
ph_size, ph_count = struct.unpack_from('<HH', original, 54)
headers = [struct.unpack_from('<IIQQQQQQ', original, ph_offset + i * ph_size)
           for i in range(ph_count)]
disassembly = Path('/root/sheng-lineage/system-bringup-r2/camera-xiaomi-disassembly.txt').read_text().splitlines()
patched = bytearray(original)
changes = []
for address in addresses:
    matches = [h for h in headers if h[0] == 1 and h[3] <= address < h[3] + h[5]]
    assert len(matches) == 1
    header = matches[0]
    offset = header[2] + address - header[3]
    assert struct.unpack_from('<I', original, offset)[0] == old_instruction
    index = next(i for i, line in enumerate(disassembly) if re.match(r'\s*' + f'{address:x}' + ':', line))
    function = next(line for line in reversed(disassembly[:index]) if re.match(r'^[0-9a-f]+ <', line))
    assert '<mihal::GraBuffer::GraBuffer(' in function, function
    assert any('_Znwm@plt' in line for line in disassembly[index + 1:index + 12])
    assert any('GraphicBufferC' in line for line in disassembly[index + 1:index + 100])
    struct.pack_into('<I', patched, offset, new_instruction)
    changes.append({'virtual_address': f'0x{address:x}', 'file_offset': offset,
                    'constructor': function.split(' <', 1)[1].rstrip(':'),
                    'old_instruction': f'{old_instruction:08x}',
                    'new_instruction': f'{new_instruction:08x}'})
assert len(original) == len(patched)
allowed = {entry['file_offset'] + i for entry in changes for i in range(4)}
assert all(i in allowed for i, (before, after) in enumerate(zip(original, patched)) if before != after)
destination = workspace / 'artifacts/camera-graphicbuffer-sheng-r1'
destination.mkdir(exist_ok=True)
output = destination / 'camera.xiaomi.so'
output.write_bytes(patched)
report = {'source_sha256': original_hash, 'patched_sha256': hashlib.sha256(patched).hexdigest(),
          'old_allocation_bytes': 256, 'required_allocation_bytes': size,
          'abi_measurement': 'exact current vendor libui compilation flags',
          'changes': changes, 'original_firmware_unchanged': True,
          'hardware_tested': False}
(destination / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(workspace / 'reports/camera-graphicbuffer-allocation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

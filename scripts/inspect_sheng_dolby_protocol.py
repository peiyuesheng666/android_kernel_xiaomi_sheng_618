#!/usr/bin/env python3
"""Read the original Dolby dispatch tables; never modify firmware."""
from pathlib import Path
import struct
root = Path('/root/sheng-lineage/lineage-24.0/vendor/xiaomi/sheng/proprietary/vendor/lib64')
def memory(path, address, count):
    data = path.read_bytes()
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', data, 54)
    for i in range(phnum):
        segment = struct.unpack_from('<IIQQQQQQ', data, phoff + phsize*i)
        kind, _, offset, virtual, _, size, _, _ = segment
        if kind == 1 and virtual <= address and address + count <= virtual + size:
            return data[offset+address-virtual:offset+address-virtual+count]
    raise ValueError(hex(address))
for name, address, count, base in (
    ('soundfx/libhwdap.so', 0xcc68, 22, 0x232cc),
    ('libdlbdsservice.so', 0x20964, 13, 0x6531c)):
    print(name)
    for key, branch in enumerate(memory(root/name, address, count)):
        print(f'  parameter={key} handler=0x{base+branch*4:x}')

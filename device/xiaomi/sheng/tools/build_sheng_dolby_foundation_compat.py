#!/usr/bin/env python3
"""Isolate foundation symbols and its pre-delivery-status AHandler ABI for Dolby.

The stock DAP and pregain handlers put their ALooper pointer at offset 96, where
modern AHandler puts a mutex. Never change the system/vendor foundation used
by other components. Inputs are read-only; all outputs are diagnostic copies.
"""
from pathlib import Path
import hashlib
import json
import struct

device = Path(__file__).resolve().parents[1]
workspace = device.parents[2]
rom = Path('/root/sheng-lineage/lineage-24.0')
stock = Path('/root/sheng-lineage/firmware-dump/partitions/vendor/lib64')
out = workspace / 'artifacts/audio-diagnostics-sheng/dolby-compat'
out.mkdir(parents=True, exist_ok=True)
source = rom / 'out/target/product/sheng/vendor/lib64/libstagefright_foundation.so'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(source) == 'f72c9caa7deb28268aaad92cab14cfea8f4addf3f42c7ff501904b267d724ed3'
from sheng_elf_compat import Elf

binary = Elf(source)
name = 'libshgdolby_foundation.so'

def word(address, expected, value):
    assert binary.read(address, 4) == struct.pack('<I', expected), hex(address)
    binary.patch(address, struct.pack('<I', value))

def branch(address, target):
    assert (target-address) % 4 == 0
    return 0x14000000 | (((target-address)//4) & 0x03ffffff)

# Keep onMessageReceived and the old counters/statistics; skip only the
# new status mutex/fields that overlap with stock subclass members.
word(0x1c750, 0x94006254, branch(0x1c750, 0x1c788))
word(0x1c7b4, 0xf9400261, branch(0x1c7b4, 0x1c7e8))
# Roster diagnostic queries cannot read fields absent from the legacy base.
word(0x1c9d0, 0xa9bd7bfd, 0xd65f03c0)  # setDeliveryStatus -> ret
get = 0x1ca28
binary.patch(get, struct.pack('<IIII',
    0x3900003f, 0xb900005f, 0xf900007f, 0xd65f03c0))

# Distinct symbol names prevent an already-loaded modern foundation from
# satisfying this private copy's relocations through ELF interposition.
rename = {old: old.replace('7android', '7shgdap_') for _, index, old in binary.symbols
          if index and '7android' in old}
binary.isolate(rename, name)
binary.write(out/name)
outputs = [{'name': name, 'sha256': sha(out/name), 'renamed_symbols': len(rename)}]
for relative, expected in (
    ('libdlbdsservice.so', 'ed5c4bd93b0fd3e97f8076c6d07ae2e7ca4ea15156b06d5d3e9788a6ebd57324'),
    ('soundfx/libhwdap.so', '2c8d8451a76fdcb53845b5368a7d46f5d699530d44aa499edfe64ceb76f11fe7'),
    ('libdlbpreg.so', 'aececf10f6bd1daa1abcd07a7e85da273c602339ffcd9e1aa29a4bf52e0d115c'),
    ('soundfx/libdlbvol.so', '477f7cdfd6b0c9cc45521bd3e67f17baebb6240b844a82bdf31cec8aee93ecb9')):
    original = stock / relative
    assert sha(original) == expected
    client = Elf(original)
    if relative.endswith('libhwdap.so'):
        # Speaker parameters also travel through AUDIO_DEVICE_OUT_DEFAULT.
        # The legacy fallback assumes 16 matrix coefficients; sheng supplies
        # 32. Its existing stack has room for 128 bytes before the canary.
        # Preserve FORTIFY and derive the cache length from the matrix width.
        # Every instruction/branch target is tied to the verified stock ELF.
        code = [
            0xb9400509,              # ldr w9, [x8,#4] : coefficient count
            0x7100813f,              # cmp w9, #32
            0x52800803,              # mov w3, #64 (original bound)
            0x5280004b,              # mov w11, #2
            0x54000061,              # b.ne +12
            0x52801003,              # mov w3, #128
            0x5280008b,              # mov w11, #4
            0xb90027eb,              # str w11, [sp,#36]
            0,                       # b original memcpy setup
            0xb94027e3,              # ldr w3, [sp,#36]
            0x531d7063,              # lsl w3,w3,#3
            0x11000863,              # add w3,w3,#2
            0,                       # b original cache setter
        ]
        address = client.append_code(code)
        # The appended section is not part of the old section table.
        last = len(client.data)-len(code)*4
        struct.pack_into('<I', client.data, last+8*4, branch(address+8*4, 0x174e0))
        struct.pack_into('<I', client.data, last+12*4, branch(address+12*4, 0x17508))
        assert client.read(0x174dc, 4) == struct.pack('<I', 0x52800803)
        assert client.read(0x17504, 4) == struct.pack('<I', 0x52800243)
        client.patch(0x174dc, struct.pack('<I', branch(0x174dc, address)))
        client.patch(0x17504, struct.pack('<I', branch(0x17504, address+9*4)))
    count = sum(old in rename for _, _, old in client.symbols)
    client.isolate(rename, name)
    target = out/Path(relative).name
    client.write(target)
    outputs.append({'name': target.name, 'original_sha256': expected,
                    'sha256': sha(target), 'renamed_symbols': count})
report = {'foundation_source_sha256': sha(source), 'files': outputs,
          'isolated_symbols': True, 'stock_dump_unchanged': True,
          'runtime_verified': False}
(out/'build-result.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))

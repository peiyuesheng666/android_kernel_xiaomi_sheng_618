#!/usr/bin/env python3
"""Shorten the identified NT36532 boot work delay in a Recovery module copy.

The input must be the exact audited OEM ELF. Only one MOV immediate changes;
the queued firmware callback, locking, metadata and ABI tables stay identical.
"""
import hashlib
import importlib.util
from pathlib import Path
import struct

ORIGINAL_SHA256 = 'a1f3f907f4519eaf3d63243561fc32c7f75337188a3953b3857bcad60135233f'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_module(path, delay_ms, kernel_hz):
    path = Path(path)
    assert delay_ms == 1000 and kernel_hz == 250
    original = path.read_bytes()
    assert sha(original) == ORIGINAL_SHA256, 'Unknown OEM touch module; refuse patch'
    assert not original.endswith(b'~Module signature appended~\n'), 'Signed module requires separate review'
    workspace = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('touch_module_abi', workspace / 'device/xiaomi/sheng/kernel/stock-modules/stage.py')
    abi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(abi)
    before = abi.Module(path)
    text = before.named['.text']
    symbols_section = before.named['.symtab']
    strings = before.section_data(before.sections[symbols_section[6]])
    symbols = [struct.unpack_from('<IBBHQQ', before.section_data(symbols_section), offset)
               for offset in range(0, symbols_section[5], 24)]
    names = [before.string(strings, item[0]) for item in symbols]
    probe = symbols[names.index('nvt_ts_probe')]
    assert probe[4] == 0x5ee8 and probe[5] == 0x2124
    assert before.sections[probe[3]] == text
    callback = symbols[names.index('Boot_Update_Firmware.cfi_jt')]
    assert callback[4] == 0x618
    relocation_sections = [section for section in before.sections
                           if section[1] == 4 and section[7] == probe[3]]
    assert len(relocation_sections) == 1
    relocation_section = relocation_sections[0]
    assert before.sections[relocation_section[6]] == symbols_section and relocation_section[9] == 24
    relocations = [struct.unpack_from('<QQq', before.section_data(relocation_section), offset)
                   for offset in range(0, relocation_section[5], 24)]
    queue_calls = [(offset, info, addend) for offset, info, addend in relocations
                   if names[info >> 32] == 'queue_delayed_work_on' and probe[4] <= offset < probe[4] + probe[5]]
    assert len(queue_calls) == 1
    assert queue_calls[0][0] == 0x7028 and queue_calls[0][2] == 0 and queue_calls[0][1] & 0xffffffff == 283
    assert any(offset == 0x6fe4 and names[info >> 32] == 'Boot_Update_Firmware.cfi_jt'
               for offset, info, addend in relocations)
    # x0=CPU, x1=workqueue, x2=delayed_work, x3=delay in jiffies.
    context_offset = text[4] + 0x7018
    expected_context = struct.pack('<5I', 0x52800400, 0xf94002a1, 0x5281b583, 0x91004102, 0x94000000)
    assert original[context_offset:context_offset + 20] == expected_context
    instruction_offset = text[4] + 0x7020
    ticks = delay_ms * kernel_hz // 1000
    replacement = struct.pack('<I', 0x52800003 | (ticks << 5))
    patched = original[:instruction_offset] + replacement + original[instruction_offset + 4:]
    assert len(patched) == len(original)
    assert patched[:instruction_offset] == original[:instruction_offset]
    assert patched[instruction_offset + 4:] == original[instruction_offset + 4:]
    path.write_bytes(patched)
    after = abi.Module(path)
    assert after.imports() == before.imports() and after.exports() == before.exports()
    assert after.info == before.info
    for name in before.named:
        if name not in ('.text', '.bss') and before.named[name][1] != 8:
            assert after.section_data(after.named[name]) == before.section_data(before.named[name]), name
    return {
        'module': path.name, 'kind': 'recovery-only-guarded-ELF-instruction-patch',
        'original_sha256': sha(original), 'patched_sha256': sha(patched),
        'symbol': 'nvt_ts_probe', 'text_address': '0x7020', 'file_offset': instruction_offset,
        'original_instruction_hex': original[instruction_offset:instruction_offset + 4].hex(),
        'patched_instruction_hex': replacement.hex(), 'kernel_hz': kernel_hz,
        'old_delay_jiffies': 3500, 'new_delay_jiffies': ticks,
        'old_delay_ms': 14000, 'new_delay_ms': delay_ms,
        'unchanged': ['firmware callback', 'firmware bytes', 'locking', 'vermagic', 'module metadata',
                      'import CRCs', 'export CRCs', 'all bytes outside one instruction'],
    }

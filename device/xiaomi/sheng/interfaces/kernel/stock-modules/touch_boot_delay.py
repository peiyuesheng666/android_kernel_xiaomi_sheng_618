#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Queue OEM touch firmware immediately after successful probe initialization.

The exact OEM ELF is required. Reuse the final diagnostic timestamp block,
leaving the firmware callback, locks, ABI and failure exits intact.
"""
import hashlib
import struct

ORIGINAL_SHA256 = 'a1f3f907f4519eaf3d63243561fc32c7f75337188a3953b3857bcad60135233f'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_bytes(original, module_class, delay_ms=0, kernel_hz=250):
    assert delay_ms == 0 and kernel_hz == 250
    assert sha(original) == ORIGINAL_SHA256, 'Unknown OEM touch module; refuse patch'
    assert not original.endswith(b'~Module signature appended~\n'), 'Signed module requires separate review'
    before = module_class('nt36532_touch.ko', data=original)
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
    # A zero delay at the original site can race __mutex_init(ts + 0x240),
    # called later at 0x76f4 and used by update_pen_status in the callback.
    # Disable the early queue and reuse only the final success-path log block.
    # Both normal and nonfatal panel-info exits reach this block after
    # add_common_data_to_buf; fatal cleanup paths never reach it.
    patched = bytearray(original)
    changed_ranges = []

    def words(address, values):
        offset = text[4] + address
        content = struct.pack('<' + 'I' * len(values), *values)
        patched[offset:offset + len(content)] = content
        changed_ranges.append((offset, offset + len(content)))

    nop = 0xd503201f
    words(0x7018, [nop] * 5)
    # x22 retains the page of ts throughout probe. Relocations below supply
    # the actual ts and nvt_fwu_wq offsets; no absolute address is embedded.
    queue_words = [
        0xf94002c8,  # ldr x8, [x22]       ; ts
        0x90000001,  # adrp x1, nvt_fwu_wq
        0xf9400021,  # ldr x1, [x1]        ; nvt_fwu_wq
        0x52800400,  # mov w0, #32         ; WORK_CPU_UNBOUND
        0x91004102,  # add x2, x8, #0x10   ; delayed_work
        0x52800003,  # mov w3, #0          ; no timer delay
        0x94000000,  # bl queue_delayed_work_on
    ]
    words(0x7fa4, queue_words + [nop] * (24 - len(queue_words)))
    assert struct.unpack_from('<2I', original, text[4] + 0x8004) == (0x2a1f03f4, 0x17fff7e3)
    by_offset = {offset: (info, addend) for offset, info, addend in relocations}
    assert (by_offset[0x701c][0] & 0xffffffff) == 286
    assert (by_offset[0x7fb8][0] & 0xffffffff) == 283
    assert names[by_offset[0x7fb8][0] >> 32] == 'ktime_get_real_ts64'
    assert names[by_offset[0x8000][0] >> 32] == '_printk'
    wq_adrp = [r for r in relocations if r[2] == 0x18
               and r[1] >> 32 == by_offset[0x701c][0] >> 32 and (r[1] & 0xffffffff) == 275
               and probe[4] <= r[0] < 0x7018]
    assert len(wq_adrp) == 1
    new_relocations = {
        0x7fa4: by_offset[0x7014],
        0x7fa8: (wq_adrp[0][1], wq_adrp[0][2]),
        0x7fac: by_offset[0x701c],
        0x7fbc: by_offset[0x7028],
    }
    # Preserve ELF/section layout by reusing existing relocation slots. NONE
    # entries are explicitly supported by the pinned arm64 module loader.
    slots = [i for i, (offset, _, _) in enumerate(relocations)
             if 0x7018 <= offset < 0x702c or 0x7fa4 <= offset < 0x8004]
    assert len(slots) >= len(new_relocations)
    entries = [(offset, info, addend) for offset, (info, addend) in sorted(new_relocations.items())]
    entries += [(0x7fa4, 0, 0)] * (len(slots) - len(entries))
    for index, entry in zip(slots, entries):
        offset = relocation_section[4] + index * 24
        patched[offset:offset + 24] = struct.pack('<QQq', *entry)
        changed_ranges.append((offset, offset + 24))
    patched = bytes(patched)
    assert len(patched) == len(original)
    for start, end in zip([0] + [b for a, b in sorted(changed_ranges)],
                          [a for a, b in sorted(changed_ranges)] + [len(original)]):
        assert patched[start:end] == original[start:end]
    after = module_class('nt36532_touch.ko', data=patched)
    assert after.imports() == before.imports() and after.exports() == before.exports()
    assert after.info == before.info
    for name in before.named:
        if before.named[name] not in (text, relocation_section) and before.named[name][1] != 8:
            assert after.section_data(after.named[name]) == before.section_data(before.named[name]), name
    return patched, {
        'module': 'nt36532_touch.ko', 'kind': 'guarded-probe-tail-immediate-firmware-work',
        'original_sha256': sha(original), 'patched_sha256': sha(patched),
        'symbol': 'nvt_ts_probe', 'old_queue_address': '0x7028', 'new_queue_address': '0x7fbc',
        'changed_file_ranges': changed_ranges, 'kernel_hz': kernel_hz,
        'old_delay_jiffies': 3500, 'new_delay_jiffies': 0,
        'old_delay_ms': 14000, 'new_delay_ms': delay_ms,
        'unchanged': ['firmware callback', 'firmware bytes', 'locking', 'vermagic', 'module metadata',
                      'import CRCs', 'export CRCs', 'fatal probe exits', 'ELF section layout'],
        'removed_diagnostic': 'final probe timestamp printk only',
    }

#!/usr/bin/env python3
"""Resize reviewed OEM GraphicBuffer heap allocations using the current vendor ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

INPUTS = {
    'camera.xiaomi.so': ('b6e893bcb30eb763290ece2e5b49d1b89809410f0628f26e7f7606106321b753',
                        [0xe6ab0, 0xe6fe4, 0xe73e8, 0xe74b0]),
    'libcom.xiaomi.grallocutils.so': ('3d65cbe8f0a211146b7d83c6cbfd03db5ec418f26d25e413b9738cb9a8314579',
                                    [0x20fc, 0x2224, 0x2480]),
    'libcom.xiaomi.mawutils.so': ('f2af70f74608fece1978688f0c54ba623a5cb09ccd91bf4746b43ee4d56902bb',
                                [0x1339c]),
    'libmis_plugin_vidhance.so': ('b5884cfb15529b76fd323822524027050d0b4f253907d162e11807d23841c69e',
                                [0x14744, 0x235a0, 0x23d6c]),
    # The two decoder inputs already contain r24's separate AHandler fix.
    'c2.dolby.hevc.dec.so': ('e004fea7dcc80fd81003a7dd225b2d77eace4b01ee178ebdbdad6960fd4aa3d4', [0xf034]),
    'c2.dolby.hevc.enc.so': ('41895db61156d7998893eb5e260687c3631f2c4e7b6442dc01994c90a762e9ca', [0xe848]),
    'c2.dolby.hevc.sec.dec.so': ('acd6104228152447b0c9b657594eafc6695e928f5ba428ad5d7e252affdcf221', [0xf044]),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sections(data, expected_type):
    require(data[:7] == b'\x7fELF\x02\x01\x01', 'Expected little-endian ELF64')
    require(struct.unpack_from('<HH', data, 16) == (expected_type, 183), 'Expected AArch64 ELF type')
    offset = struct.unpack_from('<Q', data, 40)[0]
    width, count, strings_index = struct.unpack_from('<HHH', data, 58)
    require(width == 64 and 0 < strings_index < count and offset + count * width <= len(data),
            'Invalid ELF section table')
    table = [struct.unpack_from('<IIQQQQIIQQ', data, offset + n * width) for n in range(count)]
    names_section = table[strings_index]
    names = data[names_section[4]:names_section[4] + names_section[5]]
    result = {}
    for section in table:
        name = names[section[0]:].split(b'\0', 1)[0].decode()
        require(name not in result, 'Duplicate section')
        require(section[1] == 8 or section[4] + section[5] <= len(data), 'Section outside file')
        result[name] = section
    return result, table


def layout_size(archive):
    require(archive.startswith(b'!<arch>\n'), 'Expected a regular ELF archive')
    offset = 8
    symbols = {}
    while offset < len(archive):
        header = archive[offset:offset + 60]
        require(len(header) == 60 and header[58:60] == b'`\n', 'Invalid archive header')
        size = int(header[48:58])
        require(size >= 0 and offset + 60 + size <= len(archive), 'Truncated archive member')
        member = archive[offset + 60:offset + 60 + size]
        offset += 60 + size + size % 2
        if not member.startswith(b'\x7fELF'):
            continue  # GNU symbol/name tables.
        entries, table = sections(member, 1)
        symtab = entries['.symtab']
        require(symtab[9] == 24 and symtab[5] % 24 == 0, 'Invalid ELF symbols')
        strings = table[symtab[6]]
        names = member[strings[4]:strings[4] + strings[5]]
        for at in range(symtab[4], symtab[4] + symtab[5], 24):
            name, info, _, index, _, length = struct.unpack_from('<IBBHQQ', member, at)
            name = names[name:].split(b'\0', 1)[0].decode()
            if name not in ('sheng_graphicbuffer_size', 'sheng_graphicbuffer_alignment'):
                continue
            require(index != 0 and info == 0x11 and name not in symbols, 'Invalid layout symbol')
            symbols[name] = length
    require(offset == len(archive), 'Invalid archive alignment')
    require(set(symbols) == {'sheng_graphicbuffer_size', 'sheng_graphicbuffer_alignment'},
            'Missing compiler layout symbols')
    require(symbols['sheng_graphicbuffer_alignment'] == 8, 'Unreviewed class alignment')
    size = symbols['sheng_graphicbuffer_size']
    require(size in (256, 3376), 'Unreviewed GraphicBuffer size')
    return size


def patch(source, name, size):
    expected, sites = INPUTS[name]
    require(hashlib.sha256(source).hexdigest() == expected, 'Unreviewed OEM input')
    entries, _ = sections(source, 3)
    text = entries['.text']
    output = bytearray(source)
    restore = bytearray(source)
    offsets = []
    for address in sites:
        require(text[3] <= address and address + 4 <= text[3] + text[5], 'Allocation outside text')
        at = text[4] + address - text[3]
        require(struct.unpack_from('<I', source, at)[0] == 0x52802000, 'Expected mov w0, #256')
        struct.pack_into('<I', output, at, 0x52800000 | (size << 5))
        offsets.append(at)
    restore[:] = output
    for at in offsets:
        restore[at:at + 4] = source[at:at + 4]
    require(restore == source and len(output) == len(source), 'Unrelated bytes changed')
    return bytes(output), sites


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--name', choices=INPUTS, required=True)
    args = parser.parse_args()
    require(args.output.resolve() != args.input.resolve() and not args.output.is_symlink(),
            'Generated output must not replace an input')
    size = layout_size(args.layout.read_bytes())
    output, sites = patch(args.input.read_bytes(), args.name, size)
    args.output.write_bytes(output)
    print(json.dumps(dict(file=args.name, graphic_buffer_bytes=size,
                          allocation_sites=[hex(n) for n in sites],
                          sha256=hashlib.sha256(output).hexdigest())))


if __name__ == '__main__':
    main()

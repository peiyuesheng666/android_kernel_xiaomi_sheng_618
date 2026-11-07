#!/usr/bin/env python3
"""Checked, address-preserving ELF edits for device-owned compatibility blobs."""
import struct

class Elf:
    """Edit in place, preserving every segment address and packed relocation."""
    def __init__(self, path):
        self.data = bytearray(path.read_bytes())
        shoff = struct.unpack_from('<Q', self.data, 40)[0]
        shsize, shnum, shstr = struct.unpack_from('<HHH', self.data, 58)
        sections = [struct.unpack_from('<IIQQQQIIQQ', self.data, shoff+i*shsize)
                    for i in range(shnum)]
        strings = sections[shstr]
        names = self.data[strings[4]:strings[4]+strings[5]]
        self.sections = {bytes(names[s[0]:]).split(b'\0', 1)[0].decode(): s for s in sections}
        self.strings = self.sections['.dynstr']
        sym = self.sections['.dynsym']
        self.symbols = []
        for offset in range(sym[4], sym[4]+sym[5], sym[9]):
            name, info, other, index, value, size = struct.unpack_from('<IBBHQQ', self.data, offset)
            self.symbols.append((name, index, self.string(name)))
    def string(self, index):
        return bytes(self.data[self.strings[4]+index:]).split(b'\0', 1)[0].decode()
    def replace(self, index, new):
        old = self.string(index).encode()
        new = new.encode()
        assert len(new) <= len(old)
        start = self.strings[4]+index
        self.data[start:start+len(old)] = new + b'\0'*(len(old)-len(new))
    def patch(self, address, content):
        for section in self.sections.values():
            if section[3] <= address and address+len(content) <= section[3]+section[5] and section[1] != 8:
                at = section[4]+address-section[3]
                self.data[at:at+len(content)] = content
                return
        raise ValueError(hex(address))
    def read(self, address, size):
        for section in self.sections.values():
            if section[3] <= address and address+size <= section[3]+section[5] and section[1] != 8:
                at = section[4]+address-section[3]
                return self.data[at:at+size]
        raise ValueError(hex(address))
    def isolate(self, rename, soname):
        # Same-length names prevent shifts and preserve relative code/data
        # references. GNU hash uses one bucket, keeping dynsym indices intact.
        for index, _, old in self.symbols:
            if old in rename:
                self.replace(index, rename[old])
        for index, _, old in self.symbols:
            assert self.string(index) == rename.get(old, old), old
        dyn = self.sections['.dynamic']
        for offset in range(dyn[4], dyn[4]+dyn[5], 16):
            tag, index = struct.unpack_from('<QQ', self.data, offset)
            if tag in (1, 14) and self.string(index) == 'libstagefright_foundation.so':
                self.replace(index, soname)
        table = self.sections['.gnu.hash']
        _, first, _, shift = struct.unpack_from('<IIII', self.data, table[4])
        hashes = []
        bloom = 0
        for index, _, _ in self.symbols[first:]:
            value = 5381
            for byte in self.string(index).encode():
                value = (value*33 + byte) & 0xffffffff
            hashes.append(value & ~1)
            bloom |= (1 << (value % 64)) | (1 << ((value >> shift) % 64))
        hashes[-1] |= 1
        content = struct.pack('<IIIIQI', 1, first, 1, shift, bloom, first)
        content += struct.pack('<'+'I'*len(hashes), *hashes)
        assert len(content) <= table[5]
        self.data[table[4]:table[4]+table[5]] = content + b'\0'*(table[5]-len(content))
    def write(self, path):
        path.write_bytes(self.data)
    def append_code(self, words):
        # Move only the program-header table into the new load segment; all
        # original segments, section addresses and packed relocations stay put.
        oldoff = struct.unpack_from('<Q', self.data, 32)[0]
        size, count = struct.unpack_from('<HH', self.data, 54)
        assert size == 56
        headers = [list(struct.unpack_from('<IIQQQQQQ', self.data, oldoff+i*size))
                   for i in range(count)]
        align = lambda n: (n+0x3fff) & ~0x3fff
        offset = align(len(self.data))
        virtual = align(max(p[3]+p[6] for p in headers if p[0] == 1))
        codeoff = ((count+1)*size + 15) & ~15
        code = struct.pack('<'+'I'*len(words), *words)
        length = codeoff+len(code)
        for p in headers:
            if p[0] == 6:
                p[2:7] = [offset, virtual, virtual, (count+1)*size, (count+1)*size]
        headers.append([1, 5, offset, virtual, virtual, length, length, 0x4000])
        struct.pack_into('<Q', self.data, 32, offset)
        struct.pack_into('<H', self.data, 56, count+1)
        self.data.extend(b'\0'*(offset-len(self.data)))
        table = b''.join(struct.pack('<IIQQQQQQ', *p) for p in headers)
        self.data.extend(table + b'\0'*(codeoff-len(table)) + code)
        return virtual+codeoff


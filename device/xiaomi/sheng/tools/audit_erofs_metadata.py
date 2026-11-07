#!/usr/bin/env python3
"""Read EROFS inode metadata/xattrs without requiring host SELinux support.

Format follows external/erofs-utils/include/erofs_fs.h. File contents are
independently checked by fsck.erofs; directory blocks are uncompressed.
"""
from pathlib import Path
import struct

def metadata(image):
    with Path(image).open('rb') as stream:
        def read(offset, size):
            stream.seek(offset)
            value = stream.read(size)
            assert len(value) == size
            return value
        sb = read(1024, 128)
        assert struct.unpack_from('<I', sb)[0] == 0xe0f5e1e2
        block = 1 << sb[12]
        root = struct.unpack_from('<H', sb, 14)[0]
        meta_block, xattr_block = struct.unpack_from('<II', sb, 40)
        assert sb[91] == 0, 'Long xattr prefixes require explicit decoding.'
        results = {}
        def inode(nid):
            offset = meta_block*block+nid*32
            header = read(offset, 64)
            format_, count, mode = struct.unpack_from('<HHH', header)
            extended = format_ & 1
            length = 64 if extended else 32
            size = struct.unpack_from('<Q' if extended else '<I', header, 8)[0]
            data_block = struct.unpack_from('<I', header, 16)[0]
            uid, gid = struct.unpack_from('<II' if extended else '<HH', header, 24)
            xsize = 12+(count-1)*4 if count else 0
            attrs = {}
            def entry(where):
                name_size, index, value_size = struct.unpack('<BBH', read(where, 4))
                assert not index & 0x80
                name = read(where+4, name_size)
                value = read(where+4+name_size, value_size)
                key = str(index)+':'+name.decode()
                attrs[key] = value.hex()
                return (4+name_size+value_size+3) & ~3
            if xsize:
                body = read(offset+length, xsize)
                shared_count = body[4]
                cursor = 12+shared_count*4
                assert cursor <= xsize
                for item in range(shared_count):
                    shared = struct.unpack_from('<I', body, 12+item*4)[0]
                    entry(xattr_block*block+shared*4)
                while cursor < xsize:
                    cursor += entry(offset+length+cursor)
                assert cursor == xsize
            return offset, length, xsize, mode, uid, gid, size, data_block, (format_>>1)&7, attrs
        def walk(nid, path):
            offset, length, xsize, mode, uid, gid, size, data_block, layout, attrs = inode(nid)
            results[path] = dict(mode=mode & 0o7777, uid=uid, gid=gid, xattrs=attrs)
            if mode & 0o170000 != 0o040000:
                return
            assert layout in (0, 2), 'Unsupported compressed directory'
            for index in range((size+block-1)//block):
                amount = min(block, size-index*block)
                where = offset+length+xsize if layout == 2 and amount < block else (data_block+index)*block
                data = read(where, amount)
                first_name = struct.unpack_from('<H', data, 8)[0]
                assert first_name % 12 == 0
                count = first_name//12
                entries = [struct.unpack_from('<QHBB', data, item*12) for item in range(count)]
                for item, (child_nid, name_offset, _, _) in enumerate(entries):
                    end = entries[item+1][1] if item+1 < count else len(data)
                    name = data[name_offset:end].rstrip(b'\0').decode()
                    if name not in ('.', '..'):
                        walk(child_nid, path+'/'+name)
        walk(root, '')
        return results

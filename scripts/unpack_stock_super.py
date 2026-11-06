#!/usr/bin/env python3
"""Read-only sparse-super extraction using the AOSP sparse/liblp formats.

The source is opened rb; all metadata and partition images go to --output.
No mount, flashing command, or write inside the firmware directory is used.
"""
import argparse
import bisect
import hashlib
import json
import os
from pathlib import Path
import struct


class SparseImage:
    def __init__(self, path):
        self.file = open(path, 'rb')
        header = self.file.read(28)
        magic, major, minor, fh, ch, block, blocks, chunks, checksum = struct.unpack('<I4H4I', header)
        assert magic == 0xed26ff3a and major == 1
        assert fh >= 28 and ch >= 12 and block % 4 == 0
        self.size = block * blocks
        self.segments = []
        self.starts = []
        self.file.seek(fh)
        logical = 0
        physical_size = os.fstat(self.file.fileno()).st_size
        for _ in range(chunks):
            kind, _, count, total = struct.unpack('<2H2I', self.file.read(12))
            assert total >= ch
            start = self.file.tell() - 12
            self.file.seek(start + ch)
            length = count * block
            payload = total - ch
            assert start + total <= physical_size
            if kind == 0xcac1:
                assert payload == length
                data = self.file.tell()
            elif kind == 0xcac2:
                assert payload == 4
                data = self.file.read(4)
            elif kind == 0xcac3:
                assert payload == 0
                data = b'\0' * 4
            elif kind == 0xcac4:
                assert payload == 4 and count == 0
                self.file.seek(start + total)
                continue
            else:
                raise ValueError(f'Unknown sparse chunk {kind:x}')
            if length:
                self.starts.append(logical)
                self.segments.append((logical, length, kind, data))
            logical += length
            self.file.seek(start + total)
        assert logical == self.size

    def read(self, offset, length):
        assert 0 <= offset <= self.size and offset + length <= self.size
        result = bytearray()
        while length:
            i = bisect.bisect_right(self.starts, offset) - 1
            start, size, kind, data = self.segments[i]
            delta = offset - start
            take = min(length, size - delta)
            assert take > 0
            if kind == 0xcac1:
                self.file.seek(data + delta)
                chunk = self.file.read(take)
                assert len(chunk) == take
            else:
                repeats = (delta % 4 + take + 3) // 4
                chunk = (data * repeats)[delta % 4:delta % 4 + take]
            result.extend(chunk)
            offset += take
            length -= take
        return bytes(result)


def checked_sha(data, start):
    expected = data[start:start + 32]
    modified = data[:start] + b'\0' * 32 + data[start + 32:]
    assert hashlib.sha256(modified).digest() == expected, 'Metadata checksum mismatch'


def metadata(image):
    geom = image.read(4096, 4096)
    magic, size = struct.unpack_from('<II', geom)
    assert magic == 0x616c4467 and 52 <= size <= 4096
    checked_sha(geom[:size], 8)
    max_size, slots, block_size = struct.unpack_from('<III', geom, 40)
    header = image.read(12288, 128)
    magic, major, minor, header_size = struct.unpack_from('<IHHI', header)
    assert magic == 0x414c5030 and major == 10 and minor <= 2
    assert 128 <= header_size <= max_size
    header = image.read(12288, header_size)
    checked_sha(header, 12)
    table_size = struct.unpack_from('<I', header, 44)[0]
    assert header_size + table_size <= max_size
    tables = image.read(12288 + header_size, table_size)
    assert hashlib.sha256(tables).digest() == header[48:80]

    def table(desc, expected):
        offset, count, entry_size = struct.unpack_from('<III', header, desc)
        assert entry_size == expected and offset + count * entry_size <= len(tables)
        return [tables[offset + i * entry_size:offset + (i + 1) * entry_size] for i in range(count)]

    extents = [dict(zip(('sectors', 'type', 'sector', 'source'), struct.unpack('<QIQI', e))) for e in table(92, 24)]
    devices = table(116, 64)
    assert len(devices) == 1, 'Only single-device super images are supported'
    groups = []
    for entry in table(104, 48):
        name, flags, maximum_size = struct.unpack('<36sIQ', entry)
        groups.append({'name': name.split(b'\0')[0].decode('ascii'),
                       'flags': flags, 'maximum_size': maximum_size})
    partitions = []
    for entry in table(80, 52):
        name, attributes, first, count, group = struct.unpack('<36s4I', entry)
        name = name.split(b'\0')[0].decode('ascii')
        assert name and all(c.isalnum() or c == '_' for c in name)
        assert first + count <= len(extents)
        selected = extents[first:first + count]
        for extent in selected:
            assert extent['source'] == 0 and extent['type'] in (0, 1)
            if extent['type'] == 0:
                assert (extent['sector'] + extent['sectors']) * 512 <= image.size
        partitions.append({'name': name, 'attributes': attributes, 'group': group,
                           'bytes': sum(e['sectors'] * 512 for e in selected), 'extents': selected})
    return {'super_bytes': image.size, 'metadata_slots': slots, 'groups': groups,
            'logical_block_size': block_size, 'partitions': partitions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--extract', nargs='*', default=[])
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    assert not output.is_relative_to(source.parent), 'Output must be outside the firmware image directory'
    image = SparseImage(source)
    report = metadata(image)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'super-layout.json').write_text(json.dumps(report, indent=2) + '\n')
    names = {p['name'] for p in report['partitions']}
    assert set(args.extract) <= names, f'Unknown partitions: {set(args.extract) - names}'
    for partition in report['partitions']:
        print(f"{partition['name']:20} {partition['bytes']:12,}", flush=True)
        if partition['name'] not in args.extract or not partition['bytes']:
            continue
        target = output / (partition['name'] + '.img')
        digest = hashlib.sha256()
        with target.open('xb') as f:
            for extent in partition['extents']:
                left = extent['sectors'] * 512
                offset = extent['sector'] * 512
                while left:
                    take = min(left, 8 * 1024 * 1024)
                    data = image.read(offset, take) if extent['type'] == 0 else bytes(take)
                    digest.update(data)
                    if not data.strip(b'\0'):
                        f.seek(take, 1)
                    else:
                        f.write(data)
                    left -= take
                    offset += take
            f.truncate(partition['bytes'])
        (output / (target.name + '.sha256')).write_text(f'{digest.hexdigest()}  {target.name}\n')
        print(f'Extracted {target}', flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Reconstruct selected full-OTA boot partitions and verify manifest hashes."""
import bz2
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zipfile

import audit_ota_manifest as ota


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def extract(names=('init_boot', 'vendor_boot', 'recovery')):
    destination = Path('/root/sheng-lineage/ota-boot-audit')
    destination.mkdir(exist_ok=True)
    package = ota.package
    with zipfile.ZipFile(package) as archive:
        entry = archive.getinfo('payload.bin')
        assert entry.compress_type == zipfile.ZIP_STORED
        with archive.open(entry) as payload:
            magic, major, manifest_size, signature_size = struct.unpack('>4sQQI', payload.read(24))
            assert magic == b'CrAU' and major == 2
            manifest = payload.read(manifest_size)
    manifest_fields = list(ota.fields(manifest))
    block_size = next((value for number, value in manifest_fields if number == 3), 4096)
    assert block_size == 4096
    with package.open('rb') as raw:
        raw.seek(entry.header_offset)
        local = struct.unpack('<4s5H3I2H', raw.read(30))
        assert local[0] == b'PK\x03\x04'
        blob_start = entry.header_offset + 30 + local[-2] + local[-1] + 24 + manifest_size + signature_size
        results = {}
        for number, partition_data in manifest_fields:
            if number != 13:
                continue
            partition = list(ota.fields(partition_data))
            name = next(value.decode() for number, value in partition if number == 1)
            if name not in names:
                continue
            info = dict(ota.fields(next(value for number, value in partition if number == 7)))
            size, expected = info[1], info[2].hex()
            maximum = {'system_ext': 1024**3, 'system': 2 * 1024**3,
                       'product': 4 * 1024**3, 'odm': 2 * 1024**3,
                       'vendor': 2 * 1024**3, 'vendor_dlkm': 2 * 1024**3}.get(name, 104857600)
            assert 0 < size <= maximum and size % block_size == 0
            target = destination / (name + '.img')
            if target.is_file() and target.stat().st_size == size and sha256_file(target) == expected:
                results[name] = {'path': str(target), 'sha256': expected, 'bytes': size}
                continue
            with target.open('w+b') as output:
                output.truncate(size)
                for number, operation_data in partition:
                    if number != 8:
                        continue
                    operation = list(ota.fields(operation_data))
                    scalars = {number: value for number, value in operation if number != 6}
                    extents = [dict(ota.fields(value)) for number, value in operation if number == 6]
                    extent_bytes = sum(extent[2] * block_size for extent in extents)
                    kind = scalars[1]
                    if kind in (6, 7):
                        decoded = b'\0' * extent_bytes
                    else:
                        assert kind in (0, 1, 8, 14), f'Unsupported operation {kind}'
                        offset, length = scalars[2], scalars[3]
                        assert 0 <= length <= 128 * 1024**2
                        raw.seek(blob_start + offset)
                        blob = raw.read(length)
                        assert len(blob) == length
                        if 8 in scalars:
                            assert hashlib.sha256(blob).digest() == scalars[8]
                        if kind == 0:
                            decoded = blob
                        elif kind == 1:
                            decoded = bz2.decompress(blob)
                        elif kind == 8:
                            import lzma
                            decoded = lzma.decompress(blob)
                        else:
                            decoded = subprocess.run(['zstd', '-dc'], input=blob, capture_output=True, check=True).stdout
                    assert len(decoded) == extent_bytes
                    position = 0
                    for extent in extents:
                        start, length = extent[1] * block_size, extent[2] * block_size
                        assert start + length <= size
                        output.seek(start)
                        output.write(decoded[position:position + length])
                        position += length
            assert sha256_file(target) == expected, name
            results[name] = {'path': str(target), 'sha256': expected, 'bytes': size}
    assert set(results) == set(names)
    report_path = ota.workspace / 'reports/ota-extracted-boot-images.json'
    previous = json.loads(report_path.read_text()) if report_path.exists() else {}
    previous.update(results)
    report_path.write_text(json.dumps(previous, indent=2) + '\n')
    return results


if __name__ == '__main__':
    print(json.dumps(extract(), indent=2))

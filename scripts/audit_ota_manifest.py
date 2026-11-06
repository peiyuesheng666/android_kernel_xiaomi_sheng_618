#!/usr/bin/env python3
"""Read the OTA payload manifest without extracting its partition images."""
import json
from pathlib import Path
import struct
import zipfile


def varint(data, position):
    value = 0
    for shift in range(0, 70, 7):
        assert position < len(data)
        byte = data[position]
        position += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, position
    raise ValueError('Invalid protobuf varint')


def fields(data):
    position = 0
    while position < len(data):
        tag, position = varint(data, position)
        number, wire = tag >> 3, tag & 7
        assert number > 0
        if wire == 0:
            value, position = varint(data, position)
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = data[position:position + size]
            assert len(value) == size
            position += size
        elif wire == 2:
            size, position = varint(data, position)
            value = data[position:position + size]
            assert len(value) == size
            position += size
        else:
            raise ValueError('Unsupported protobuf wire type')
        yield number, value


workspace = Path(__file__).resolve().parents[1]
package = workspace / 'artifacts/lineage-24.0-20261105-UNOFFICIAL-sheng/lineage-24.0-20261105-UNOFFICIAL-sheng.zip'
with zipfile.ZipFile(package) as archive:
    metadata = dict(line.split('=', 1) for line in archive.read('META-INF/com/android/metadata').decode().splitlines() if '=' in line)
    assert metadata['pre-device'] == 'sheng' and metadata['ota-type'] == 'AB'
    with archive.open('payload.bin') as payload:
        header = payload.read(24)
        magic, major, manifest_size, signature_size = struct.unpack('>4sQQI', header)
        assert magic == b'CrAU' and major == 2 and manifest_size < 16 * 1024**2
        manifest = payload.read(manifest_size)
        assert len(manifest) == manifest_size
partitions = []
for number, value in fields(manifest):
    if number != 13:
        continue
    partition = {}
    for item_number, item in fields(value):
        if item_number == 1:
            partition['name'] = item.decode()
        elif item_number == 7:
            for info_number, info in fields(item):
                if info_number == 1:
                    partition['bytes'] = info
                elif info_number == 2:
                    partition['sha256'] = info.hex()
    assert 'name' in partition
    partitions.append(partition)
recovery = next(item for item in partitions if item['name'] == 'recovery')
export = json.loads((package.parent / 'build-result.json').read_text())
expected = next(item['sha256'] for item in export['files'] if item['name'] == 'recovery.img')
assert recovery.get('bytes', 0) > 0 and len(recovery.get('sha256', '')) == 64
report = {'package': str(package), 'metadata': metadata, 'partitions': partitions,
          'payload_recovery_matches_original_export': recovery['sha256'] == expected,
          'payload_recovery_differs_from_r13': recovery['sha256'] != '738556589abb2c35047879f14cfed63a05a6ed25c7c418a0209709622312376f',
          'r13_recovery_sha256': '738556589abb2c35047879f14cfed63a05a6ed25c7c418a0209709622312376f'}
(workspace / 'reports/ota-install-manifest-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'package': package.name, 'partition_names': [item['name'] for item in partitions],
                  'recovery': recovery, 'payload_recovery_differs_from_r13': report['payload_recovery_differs_from_r13']}, indent=2))

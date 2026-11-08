#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate and extract two 1 MiB snapshots read from rawdump at 288 MiB."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


def decode(raw):
    results = []
    for slot in range(2):
        data = raw[slot * 1024**2:(slot + 1) * 1024**2]
        if len(data) < 64 or data[:8] != b'SH618LOG':
            continue
        magic, version, header, run, seq, ms, size, crc, total, reserved, padding = struct.unpack('<8sIIQQQIIII8s', data[:64])
        if version != 1 or header != 64 or total % 4096 or total > len(data) or total < 80:
            continue
        if size > total - 80 or reserved or padding != b'\0' * 8:
            continue
        if data[total - 16:total] != struct.pack('<8sQ', b'SH618END', seq):
            continue
        text = data[64:64 + size]
        if zlib.crc32(text) != crc:
            continue
        results.append({'slot': slot, 'run': f'{run:016x}', 'sequence': seq,
                        'uptime_ms': ms, 'bytes': size, 'text': text.decode(errors='replace')})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    args = parser.parse_args()
    raw = args.raw.read_bytes()
    assert len(raw) == 2 * 1024**2, 'Expected exactly the 288..290 MiB region'
    logs = decode(raw)
    output = []
    for log in logs:
        path = args.raw.with_name(f"bootlog-{log['run']}-{log['sequence']}.txt")
        path.write_text(log.pop('text'), encoding='utf-8')
        output.append({**log, 'file': str(path)})
    report = {'raw_sha256': hashlib.sha256(raw).hexdigest(), 'valid_snapshots': output,
              'valid_snapshot_found': bool(logs)}
    args.raw.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

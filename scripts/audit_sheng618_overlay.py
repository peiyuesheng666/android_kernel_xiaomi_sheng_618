#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inspect actual newc archive metadata, including the batch helper's mode."""
import argparse
import hashlib
import json
from pathlib import Path
import stat


def entries(raw):
    offset = 0
    while offset + 110 <= len(raw):
        assert raw[offset:offset + 6] in (b'070701', b'070702'), offset
        fields = [int(raw[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
        start = offset + 110
        name = raw[start:start + fields[11] - 1].decode()
        start = (start + fields[11] + 3) & ~3
        end = start + fields[6]
        assert end <= len(raw)
        if name == 'TRAILER!!!':
            return
        yield name.removeprefix('./'), fields[1], raw[start:end]
        offset = (end + 3) & ~3
    raise ValueError('Archive missing trailer')


def audit(path):
    raw = path.read_bytes()
    archive = {name: (mode, payload) for name, mode, payload in entries(raw)}
    mode, helper = archive['k618_umh']
    return {'archive': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
            'entry_count': len(archive),
            'module_count': sum(p.startswith('lib/modules/') and p.endswith('.ko') for p in archive),
            'helper_mode': oct(mode), 'helper_is_regular': stat.S_ISREG(mode),
            'helper_executable': stat.S_ISREG(mode) and bool(mode & 0o111),
            'helper_sha256': hashlib.sha256(helper).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cpio', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.cpio), indent=2))

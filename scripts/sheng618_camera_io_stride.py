#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check camera source receipts and reject pre-repair camera ELF payloads."""
import hashlib
import json

MARKER = b'VFE780 supplied plane stride enabled'


def verify(module, project, k618):
    receipt = project / 'reports/kernel618-camera-io-stride-source.json'
    if not receipt.is_file():
        return None
    source = json.loads(receipt.read_text())
    for name, hashes in source['files'].items():
        assert hashlib.sha256((k618 / name).read_bytes()).hexdigest() == hashes['after'], name
    if MARKER not in module.read_bytes():
        raise ValueError('VFE780 supplied-stride initialization absent from camera ELF')
    return dict(module=str(module), source_hashes_verified=True,
                vfe780_stride_initialization_present=True)

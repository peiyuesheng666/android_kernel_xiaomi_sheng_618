#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject charger payloads that omit the shipping sheng Type-C interfaces."""
import hashlib
import json

from audit_kernel618_modules import ElfModule


def verify(module, project, k618):
    receipt = project / 'reports/kernel618-usb-charger-abi-source.json'
    if not receipt.is_file():
        return None
    source = json.loads(receipt.read_text())
    for name, hashes in source['files'].items():
        assert hashlib.sha256((k618 / name).read_bytes()).hexdigest() == hashes['after'], name
    elf = ElfModule(module)
    defined = {name for name, _, index, _ in elf.symbols() if index}
    expected = {'class_attr_' + name for name in source['contracts']}
    expected |= {name + '_show' for name in source['contracts']}
    expected |= {name + '_store' for name, item in source['contracts'].items() if not item['read_only']}
    missing = sorted(expected - defined)
    if missing:
        raise ValueError('Shipping sheng Type-C attributes absent from ELF: ' + ', '.join(missing))
    assert 'class_create_file_ns' in elf.undefined()
    return dict(module=str(module), sha256=elf.digest,
                source_hashes_verified=True, class_attributes_verified=sorted(source['contracts']),
                dynamic_class_registration_import_verified=True)

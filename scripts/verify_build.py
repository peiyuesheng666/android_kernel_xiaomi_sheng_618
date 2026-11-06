#!/usr/bin/env python3
"""Validate the built architecture, release, config and module agreement."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

WORK = Path('/root/sheng-612')
DIST = WORK / 'out/ack-dist'
PROJECT = Path(__file__).resolve().parents[1]
image = (DIST / 'Image').read_bytes()
assert image[56:60] == b'ARM\x64', 'Not an ARM64 Linux Image'
release = (DIST / 'kernel.release').read_text().strip()
assert release.startswith('6.12.'), release
assert release.encode() in image, 'Kernel banner does not agree with release'
config = (DIST / 'ack.config').read_text()
required = ('CONFIG_ARM64=y', 'CONFIG_MODULES=y', 'CONFIG_MODVERSIONS=y',
            'CONFIG_RUST=y', 'CONFIG_ANDROID_BINDER_IPC=y',
            'CONFIG_ANDROID_BINDER_IPC_RUST=m', 'CONFIG_ASHMEM=y', 'CONFIG_LTO_NONE=y')
for option in required:
    assert option in config.splitlines(), f'Missing {option}'
modules = sorted((DIST / 'module-staging').rglob('*.ko'))
assert modules, 'No GKI modules were built'
module_records = []
for module in modules:
    # Without -k, kmod may return WSL's builtin metadata for a same-named module.
    vermagic = subprocess.check_output(['modinfo', '-k', release, '-F', 'vermagic', str(module)], text=True).strip()
    assert vermagic, f'Module does not expose vermagic: {module}'
    assert vermagic.split()[0] == release, f'Module release mismatch: {module}'
    with module.open('rb') as stream:
        header = stream.read(20)
    assert header[:4] == b'\x7fELF' and struct.unpack_from('<H', header, 18)[0] == 183, module
    module_records.append({'name': module.name, 'vermagic': vermagic, 'bytes': module.stat().st_size})
files = {}
for filename in ('Image', 'Image.gz', 'System.map', 'Module.symvers', 'ack.config'):
    path = DIST / filename
    files[filename] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
report = {'status': 'compiled-and-checked', 'device_boot_tested': False,
          'device_ready': False, 'release': release,
          'ack_commit': (DIST / 'source.commit').read_text().strip(),
          'build_method': 'Direct Kbuild; official GKI defconfig, including Rust/BTF and its default LTO_NONE; no Google certification or ABI certification claimed',
          'missing_for_sheng': ['SM8550/Kalama BSP and device driver migration',
                                '6.12-compatible vendor modules', 'matched board DTB/DTBO',
                                'boot/vendor_boot/module partition packaging', 'physical device boot validation'],
          'files': files, 'gki_modules': module_records}
(PROJECT / 'reports/build-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
(DIST / 'build-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'Validated ARM64 {release}, {len(modules)} matching GKI modules')

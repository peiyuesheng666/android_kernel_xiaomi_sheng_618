#!/usr/bin/env python3
"""Stage the stock, recovery-tested touch processor for a system diagnosis."""
import hashlib
import json
from pathlib import Path

workspace = Path(__file__).resolve().parents[1]
stock = Path('/root/sheng-lineage/firmware-dump/partitions/odm')
source = stock / 'bin/touch_report_debug'
tested = workspace / 'tools/sheng-touch-runtime/touch_report_debug'
data = source.read_bytes()
assert data == tested.read_bytes(), 'The recovery-tested touch processor changed'
old = b'/vendor/firmware/'
new = b'/odm/firmware////'
assert len(old) == len(new)
count = data.count(old)
assert count > 0
patched = data.replace(old, new)
assert len(patched) == len(data)
destination = workspace / 'artifacts/system-touch-runtime-sheng-r1'
destination.mkdir(exist_ok=True)
binary = destination / 'touch_report'
binary.write_bytes(patched)
binary.chmod(0o755)
report = {
    'source': str(source),
    'source_sha256': hashlib.sha256(data).hexdigest(),
    'recovery_tested_source_matched': True,
    'runtime_sha256': hashlib.sha256(patched).hexdigest(),
    'path_replacements': count,
    'path_change': ['/vendor/firmware/', '/odm/firmware////'],
    'bytes_unchanged': True,
    'system_touch_verified': False,
}
(destination / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

#!/usr/bin/env python3
"""Verify the actual QTI flag and changed shared UI library before live tests."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
candidate = Path('/root/sheng-lineage/recovery-qti-candidate')
original = Path('/root/sheng-lineage/recovery-r5/20261105T151956Z/root/system/lib64/librecovery_ui.so')
source = rom / 'out/target/product/sheng/recovery/root/system/lib64/librecovery_ui.so'
event = json.loads(Path('/root/sheng-lineage/logs/recovery-qti/build-event.json').read_text())
assert event['state'] == 'finished' and event['succeeded']
assert event['run_id'] == '2d8f1b686d6d4c8ba1084821b931c2a3'
variables = json.loads((rom / 'out/soong/soong.lineage_sheng.variables').read_text())
assert variables['VendorVars']['recovery']['target_recovery_uses_qti_drm'] in ('true', True)
assert variables['VendorVarTypes']['recovery']['target_recovery_uses_qti_drm'] == 'bool'


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def needed(file):
    output = subprocess.check_output(['aarch64-linux-gnu-readelf', '-d', str(file)], text=True)
    return sorted(re.findall(r'\(NEEDED\).*?\[(.*?)\]', output))


assert sha(source) != sha(original), 'Shared UI library did not change; do not test the old backend'
assert needed(source) == needed(original), 'Review newly required shared libraries before testing'
candidate.mkdir(exist_ok=True)
shutil.copyfile(source, candidate / source.name)
report = {'qti_flag': True, 'qti_flag_type': 'bool', 'build_run_id': event['run_id'],
          'library': source.name, 'bytes': source.stat().st_size,
          'sha256': sha(source), 'original_sha256': sha(original),
          'needed_libraries': needed(source), 'hardware_tested': False,
          'note': 'minui backend is linked into librecovery_ui.so; replacing only recovery is insufficient.'}
(candidate / 'qti-candidate.json').write_text(json.dumps(report, indent=2) + '\n')
(work / 'reports/qti-candidate.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

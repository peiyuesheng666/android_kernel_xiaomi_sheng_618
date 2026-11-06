#!/usr/bin/env python3
"""Continue to the full ROM only after this exact validation passes unchanged."""
import argparse
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys

from build_events import alive, identity, now, probe

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run-id', required=True)
args = parser.parse_args()
work = Path(__file__).resolve().parents[1]
logs = Path('/root/sheng-lineage/logs')
record = {'validation_run_id': args.run_id, 'controller': identity(os.getpid()),
          'started_at': now(), 'action': 'waiting-for-validation'}


def save():
    destination = logs / 'validation-continuation.json'
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    temporary.replace(destination)


save()
while True:
    event = probe(logs)
    assert event['run_id'] == args.run_id, 'Another run replaced the validation; do not duplicate it'
    if event['state'] != 'running':
        break
    process = next((p for p in (event.get('supervisor'), event.get('worker')) if alive(p)), None)
    if process is None:
        continue
    try:
        descriptor = os.pidfd_open(process['pid'])
    except ProcessLookupError:
        continue
    try:
        if alive(process):
            poller = select.poll()
            poller.register(descriptor, select.POLLIN)
            poller.poll()
    finally:
        os.close(descriptor)

if not event.get('succeeded') or event.get('phase') != 'prebuild-validation-passed':
    record.update(action='validation-needs-repair', finished_at=now())
    save()
    print(json.dumps(record), flush=True)
    raise SystemExit(1)

result = subprocess.run([sys.executable, str(work / 'scripts/require_validated.py')])
if result.returncode:
    record.update(action='validation-receipt-rejected', finished_at=now())
    save()
    raise SystemExit(result.returncode)

# A validation pass authorizes the next stage, never artifact delivery or flashing.
evidence = logs / 'validation-evidence' / args.run_id
evidence.mkdir(parents=True, exist_ok=True)
for source, name in ((logs / 'build-lineage.log', 'validation.log'),
                     (work / 'reports/lineage-validation.json', 'validation-result.json'),
                     (logs.parent / 'lineage-24.0/out/target/product/sheng/obj/KERNEL_OBJ/sheng-stock-module-compatibility.json', 'module-abi.json')):
    shutil.copyfile(source, evidence / name)
(logs / 'device-audit.pending').unlink(missing_ok=True)
record.update(action='starting-full-build', validation_finished_at=event['finished_at'], handoff_at=now())
save()
print(json.dumps(record), flush=True)
os.execv(sys.executable, [sys.executable, str(work / 'scripts/resume_after_source_maintenance.py')])

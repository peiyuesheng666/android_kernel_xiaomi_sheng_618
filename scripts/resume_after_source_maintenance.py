#!/usr/bin/env python3
"""Resume the same build after checking completed source-cache maintenance."""
import json
import os
from pathlib import Path
import shutil

from build_events import probe

WORK = Path(__file__).resolve().parents[1]
LOGS = Path('/root/sheng-lineage/logs')
assert (LOGS / 'rom-status.txt').read_text().strip() == 'synced'
event = probe(LOGS)
assert event['state'] != 'running', 'An existing build must not be duplicated'
report = json.loads((LOGS / 'source-cache-slimming.json').read_text())
assert len(report['projects']) == 4
assert all(row['connectivity_checked'] and row['checkout_unchanged'] for row in report['projects'])
assert shutil.disk_usage('/mnt/c').free > 25 * 1024**3
if event.get('run_id'):
    (LOGS / 'build-event-ack.json').write_text(json.dumps({
        'run_id': event['run_id'], 'action': 'Applied documented build fixes; retrying build'
    }, indent=2) + '\n')
(LOGS / 'source-maintenance.pending').unlink(missing_ok=True)
os.execvp('bash', ['bash', str(WORK / 'scripts/build_lineage.sh')])

#!/usr/bin/env python3
"""Observe a live build until five minutes without failure, publishing evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

from build_events import probe

LOGS = Path('/root/sheng-lineage/logs')
phase_file = LOGS / 'build-phase.txt'
last_print = 0
while True:
    event = probe(LOGS)
    if event['state'] != 'running':
        print(json.dumps(event), flush=True)
        raise SystemExit(0 if event.get('succeeded') else 1)
    phase = phase_file.read_text().strip()
    phase_start = phase_file.stat().st_mtime
    run_start = datetime.fromisoformat(event['started_at']).timestamp()
    elapsed = time.time() - phase_start if phase == 'building' and phase_start >= run_start else 0
    log = LOGS / 'build-lineage.log'
    tail = ''
    if log.exists():
        with log.open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 32768))
            tail = stream.read().decode(errors='replace')
    errors = bool(re.search(r'(?m)^(?:error:|FAILED:)', tail))
    if elapsed >= 300 and not errors:
        # Recheck completion/process identity before releasing the observation gate.
        final = probe(LOGS)
        if final['state'] != 'running' or final['run_id'] != event['run_id']:
            continue
        evidence = {'run_id': event['run_id'], 'observed_at': datetime.now(timezone.utc).isoformat(),
                    'building_since_epoch': phase_start, 'elapsed_building_seconds': round(elapsed, 1),
                    'phase': phase, 'exit_event': False, 'error_in_recent_log': False,
                    'recent_progress': tail.splitlines()[-5:],
                    'rom_compiled': False, 'hardware_boot_tested': False}
        (LOGS / 'build-stability.json').write_text(json.dumps(evidence, indent=2) + '\n')
        (LOGS / 'watch-five-minutes.pending').unlink(missing_ok=True)
        print(json.dumps(evidence), flush=True)
        break
    if time.monotonic() - last_print >= 30:
        print(json.dumps({'run_id': event['run_id'], 'phase': phase,
                          'elapsed_building_seconds': round(elapsed, 1),
                          'error_in_recent_log': errors}), flush=True)
        last_print = time.monotonic()
    time.sleep(15)

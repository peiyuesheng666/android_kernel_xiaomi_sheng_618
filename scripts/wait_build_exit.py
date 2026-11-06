#!/usr/bin/env python3
"""Block on Linux process-exit events; no timed model wake-ups or log reads."""
import json
import os
import select

from pathlib import Path

from build_events import alive, probe

logs = Path('/root/sheng-lineage/logs')
while True:
    event = probe(logs)
    if event['state'] != 'running':
        print(json.dumps(event), flush=True)
        raise SystemExit(0 if event.get('succeeded') else 1)
    process = next((record for record in (event.get('supervisor'), event.get('worker')) if alive(record)), None)
    if process is None:
        continue
    try:
        descriptor = os.pidfd_open(process['pid'])
    except ProcessLookupError:
        continue
    try:
        if not alive(process):
            continue
        print(json.dumps({'state': 'waiting-for-exit', 'run_id': event['run_id'], 'pid': process['pid']}), flush=True)
        poller = select.poll()
        poller.register(descriptor, select.POLLIN)
        poller.poll()
    finally:
        os.close(descriptor)

#!/usr/bin/env python3
"""Stop this task's old sync/continuation only, preserving downloaded objects."""
import json
from pathlib import Path
import os
import signal
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--branch', choices=('lineage-23.2', 'lineage-24.0'), default='lineage-23.2')
parser.add_argument('--report', default='/root/sheng-lineage/logs/migration-24/stopped-processes.json')
parser.add_argument('--status', default='migrating-to-24')
args = parser.parse_args()

processes = {}
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        command = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        status = (entry / 'status').read_text()
        parent = int(next(line.split()[1] for line in status.splitlines() if line.startswith('PPid:')))
        processes[int(entry.name)] = (parent, command)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
roots = [pid for pid, (_, cmd) in processes.items()
         if (f'/root/sheng-lineage/{args.branch}/.repo/repo/main.py ' in cmd and ' sync ' in cmd)
         or ('bash ' in cmd and '/scripts/continue_after_sync.sh ' in cmd)]
selected = set(roots)
while True:
    additions = {pid for pid, (parent, _) in processes.items() if parent in selected}
    if additions <= selected:
        break
    selected.update(additions)
assert os.getpid() not in selected
report = [{'pid': pid, 'command': processes[pid][1]} for pid in sorted(selected)]
Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
for pid in roots + sorted(selected - set(roots), reverse=True):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
Path('/root/sheng-lineage/logs/rom-status.txt').write_text(args.status + '\n')
print(f'Sent TERM to {len(selected)} task-owned processes; source objects retained')

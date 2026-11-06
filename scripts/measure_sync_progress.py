#!/usr/bin/env python3
"""Measure short-window receive rate and revision availability for the active manifest."""
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path('/root/sheng-lineage/lineage-24.0')


def received():
    rows = Path('/proc/net/dev').read_text().splitlines()[2:]
    return sum(int(row.split(':', 1)[1].split()[0]) for row in rows if row.split(':', 1)[0].strip() != 'lo')


start_time = time.monotonic()
start_bytes = received()
manifest = ET.parse('/root/sheng-lineage/logs/manifest-progress24.xml').getroot()
default = manifest.find('default').attrib
remotes = {r.get('name'): r.attrib for r in manifest.findall('remote')}
ready, pending = [], []
for project in manifest.findall('project'):
    path = project.get('path', project.get('name'))
    remote = project.get('remote', default['remote'])
    revision = project.get('revision', remotes[remote].get('revision', default['revision']))
    git = ROOT / '.repo/projects' / (path + '.git')
    if revision.startswith('refs/heads/'):
        revision = 'refs/remotes/' + remote + '/' + revision.removeprefix('refs/heads/')
    elif not revision.startswith('refs/') and not re.fullmatch('[0-9a-f]{40}', revision):
        revision = 'refs/remotes/' + remote + '/' + revision
    result = subprocess.run(['git', '--git-dir=' + str(git), 'rev-parse', '--verify', revision + '^{commit}'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (ready if result.returncode == 0 else pending).append(path)
remaining = 30 - (time.monotonic() - start_time)
if remaining > 0:
    time.sleep(remaining)
elapsed = time.monotonic() - start_time
rate = (received() - start_bytes) / elapsed
report = {'window_seconds': round(elapsed, 1), 'receive_mib_per_second': round(rate / 1024**2, 2),
          'receive_gib_per_hour': round(rate * 3600 / 1024**3, 2),
          'manifest_projects': len(ready) + len(pending), 'target_revision_available': len(ready),
          'target_revision_pending': len(pending), 'pending_paths': pending,
          'note': 'Short sample of WSL non-loopback traffic, not a guaranteed whole-download rate; repository counts are not byte progress.'}
Path('/root/sheng-lineage/logs/sync-rate24.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

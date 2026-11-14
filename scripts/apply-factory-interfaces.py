#!/usr/bin/env python3
"""Apply the pinned factory-interface overlay after the inherited repairs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

project = Path(os.environ['PROJECT_ROOT']).resolve()
root = Path(os.environ['BUILD_ROOT']).resolve()
receipt = json.loads((project / 'provenance/factory-interfaces.json').read_text())
patch = project / receipt['patch']
assert hashlib.sha256(patch.read_bytes()).hexdigest() == receipt['patch_sha256']
expected = json.loads((project / 'provenance/source-files.json').read_text())
for filename in ('charging-fix.json', 'droidspaces-fix.json', 'scene-socinfo-fix.json',
                 'pen-release-fix.json', 'repair-r85.json', 'pen-stability.json'):
    path = project / 'provenance' / filename
    if path.exists():
        for name, record in json.loads(path.read_text())['files'].items():
            expected[name] = record['after']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


states = set()
for name, record in receipt['files'].items():
    assert expected.get(name) == record['before'], 'Overlay base mismatch: ' + name
    got = sha(root / name)
    if got == record['after']:
        states.add('after')
    elif got == record['before']:
        states.add('before')
    else:
        raise SystemExit('Unexpected factory interface source: ' + name)
assert len(states) == 1, 'Partially applied factory interface overlay'
if '--check' in sys.argv:
    assert states == {'after'}, 'Factory interface overlay is not applied'
elif states == {'before'}:
    subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch)],
                   cwd=root, check=True)
for name, record in receipt['files'].items():
    assert sha(root / name) == record['after'], name
print('Verified factory interface overlay: ' + receipt['revision'])

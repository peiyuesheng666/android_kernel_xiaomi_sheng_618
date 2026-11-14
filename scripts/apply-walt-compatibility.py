#!/usr/bin/env python3
"""Replay and verify the pinned Qualcomm WALT compatibility overlay."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

project = Path(os.environ['PROJECT_ROOT']).resolve()
root = Path(os.environ['BUILD_ROOT']).resolve()
receipt = json.loads((project / 'provenance/walt-compatibility.json').read_text())
patch = project / receipt['patch']
assert hashlib.sha256(patch.read_bytes()).hexdigest() == receipt['patch_sha256']
expected = json.loads((project / 'provenance/source-files.json').read_text())
for filename in ('charging-fix.json', 'droidspaces-fix.json', 'scene-socinfo-fix.json',
                 'pen-release-fix.json', 'repair-r85.json', 'pen-stability.json',
                 'factory-interfaces.json'):
    for name, record in json.loads((project / 'provenance' / filename).read_text())['files'].items():
        expected[name] = record['after']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


states = set()
for name, record in receipt['files'].items():
    assert expected.get(name) == record['before'], 'WALT base mismatch: ' + name
    got = sha(root / name)
    if record['before'] == record['after']:
        assert got == record['after'], name
    elif got == record['after']:
        states.add('after')
    elif got == record['before']:
        states.add('before')
    else:
        raise SystemExit('Unexpected WALT source: ' + name)
assert len(states) == 1, 'Partially applied WALT overlay'
if '--check' in sys.argv:
    assert states == {'after'}, 'WALT overlay is not applied'
elif states == {'before'}:
    subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', str(patch)],
                   cwd=root, check=True)
for name, record in receipt['files'].items():
    assert sha(root / name) == record['after'], name
print('Verified Qualcomm WALT overlay: ' + receipt['revision'])

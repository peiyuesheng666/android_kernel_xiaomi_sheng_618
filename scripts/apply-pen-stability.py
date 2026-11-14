#!/usr/bin/env python3
"""Apply only the two reviewed pen driver files on a verified r87 base."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

project = Path(os.environ['PROJECT_ROOT']).resolve()
root = Path(os.environ['BUILD_ROOT']).resolve()
receipt = json.loads((project / 'provenance/pen-stability.json').read_text())
patch = project / receipt['patch']
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(patch) == receipt['patch_sha256'], 'Pen patch hash mismatch'
for name, expected in receipt['unchanged_files'].items():
    assert sha(root / name) == expected, 'Protected r87 source differs: ' + name
states = set()
for name, entry in receipt['files'].items():
    path = root / name
    assert path.resolve().is_relative_to(root), path
    got = sha(path)
    if got == entry['after']:
        states.add('after')
    elif got == entry['before']:
        states.add('before')
    else:
        raise RuntimeError('Unexpected pen driver source: ' + name)
assert len(states) == 1, 'Partial pen stability source patch'
if '--check' in sys.argv:
    assert states == {'after'}, 'Pen patch has not been applied'
elif states == {'before'}:
    subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)], cwd=root, check=True)
for name, entry in receipt['files'].items():
    assert sha(root / name) == entry['after'], name
for name, expected in receipt['unchanged_files'].items():
    assert sha(root / name) == expected, 'Protected r87 source changed: ' + name
print('Verified pen stability patch; panic, reboot, traps and 32 ms filter sources unchanged', flush=True)

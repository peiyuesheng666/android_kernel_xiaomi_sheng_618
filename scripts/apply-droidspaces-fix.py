#!/usr/bin/env python3
"""Apply the official GKI 6.12+ SYSVIPC layout fix with pinned source hashes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

project = Path(os.environ['PROJECT_ROOT']).resolve()
root = Path(os.environ['BUILD_ROOT']).resolve()
receipt = json.loads((project / 'provenance/droidspaces-fix.json').read_text())
patch = project / receipt['patch']
assert hashlib.sha256(patch.read_bytes()).hexdigest() == receipt['patch_sha256']
base = json.loads((project / 'provenance/source-files.json').read_text())
states = set()
for name, hashes in receipt['files'].items():
    assert base[name] in (hashes['before'], hashes['after']), name
    got = hashlib.sha256((root / name).read_bytes()).hexdigest()
    if got == hashes['after']:
        states.add('after')
    elif got == hashes['before']:
        states.add('before')
    else:
        raise SystemExit('Unexpected Droidspaces source: ' + name)
assert len(states) == 1, 'Partially applied Droidspaces patch'
if '--check' in sys.argv:
    assert states == {'after'}, 'Droidspaces fix has not been applied'
elif states == {'before'}:
    subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)],
                   cwd=root, check=True)
for name, hashes in receipt['files'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == hashes['after'], name
print('Verified official Droidspaces GKI 6.12+ SYSVIPC compatibility patch')

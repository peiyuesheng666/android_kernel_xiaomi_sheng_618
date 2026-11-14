#!/usr/bin/env python3
"""Restore the official KALAMAP SoC ID, with pinned source/patch hashes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


# Factory interface overlay: allow only its pinned final source, never an arbitrary edit.
def factory_interface_matches(name, got):
    path = Path(os.environ['PROJECT_ROOT']) / 'provenance/factory-interfaces.json'
    if not path.exists():
        return False
    item = json.loads(path.read_text())['files'].get(name)
    return bool(item and item['after'] == got)


project = Path(os.environ['PROJECT_ROOT']).resolve()
root = Path(os.environ['BUILD_ROOT']).resolve()
receipt = json.loads((project / 'provenance/scene-socinfo-fix.json').read_text())
patch = project / receipt['patch']
assert hashlib.sha256(patch.read_bytes()).hexdigest() == receipt['patch_sha256']
base = json.loads((project / 'provenance/source-files.json').read_text())
states = set()
for name, hashes in receipt['files'].items():
    assert base[name] in (hashes['before'], hashes['after']), name
    got = hashlib.sha256((root / name).read_bytes()).hexdigest()
    if (got == hashes['after'] or factory_interface_matches(name, got)):
        states.add('after')
    elif got == hashes['before']:
        states.add('before')
    else:
        raise SystemExit('Unexpected SoC source: ' + name)
assert len(states) == 1, 'Partially applied SoC patch'
if '--check' in sys.argv:
    assert states == {'after'}, 'KALAMAP SoC fix has not been applied'
elif states == {'before'}:
    subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)], cwd=root, check=True)
for name, hashes in receipt['files'].items():
    got = hashlib.sha256((root / name).read_bytes()).hexdigest()
    assert (got == hashes['after'] or factory_interface_matches(name, got)), name
print('Verified official SoC ID 536 -> KALAMAP mapping')

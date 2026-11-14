#!/usr/bin/env python3
"""Apply the hash-pinned sheng dual-battery authentication interface fix."""
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
receipt = json.loads((project / 'provenance/charging-fix.json').read_text())
patch = project / receipt['patch']
assert hashlib.sha256(patch.read_bytes()).hexdigest() == receipt['patch_sha256']
base = json.loads((project / 'provenance/source-files.json').read_text())
repair_path = project / 'provenance/repair-r85.json'
repair = json.loads(repair_path.read_text())['files'] if repair_path.exists() else {}
def repaired(name, got):
    return name in repair and got == repair[name]['after']
states = set()
for name, hashes in receipt['files'].items():
    assert base[name] in (hashes['before'], hashes['after']), name
    got = hashlib.sha256((root / name).read_bytes()).hexdigest()
    downstream = json.loads((project / 'provenance/pen-release-fix.json').read_text())['files'].get(name)
    if (got == hashes['after'] or factory_interface_matches(name, got)) or (downstream and got == downstream['after']) or repaired(name, got):
        states.add('after')
    elif got == hashes['before']:
        states.add('before')
    else:
        raise SystemExit('Unexpected charging source: ' + name)
assert len(states) == 1, 'Partially applied charging patch'
if '--check' in sys.argv:
    assert states == {'after'}, 'Charging fix has not been applied'
elif states == {'before'}:
    subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)],
                   cwd=root, check=True)
for name, hashes in receipt['files'].items():
    got = hashlib.sha256((root / name).read_bytes()).hexdigest()
    downstream = json.loads((project / 'provenance/pen-release-fix.json').read_text())['files'].get(name)
    assert (got == hashes['after'] or factory_interface_matches(name, got)) or (downstream and got == downstream['after']) or repaired(name, got), name
print('Verified sheng slave-battery authentication patch (firmware property 165)')

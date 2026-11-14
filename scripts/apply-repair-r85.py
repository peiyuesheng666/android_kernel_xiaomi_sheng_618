#!/usr/bin/env python3
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


project=Path(os.environ['PROJECT_ROOT']).resolve()
root=Path(os.environ['BUILD_ROOT']).resolve()
receipt=json.loads((project/'provenance/repair-r85.json').read_text())
patch=project/receipt['patch']
overlay=json.loads((project/'provenance/pen-stability.json').read_text())['files']
def overlay_matches(name, got):
    item=overlay.get(name)
    if not item or item['after']!=got:return False
    assert item['before']==receipt['files'][name]['after'],name
    return True
assert hashlib.sha256(patch.read_bytes()).hexdigest()==receipt['patch_sha256']
states=set()
for name,entry in receipt['files'].items():
    path=root/name
    got=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    if (got==entry['after'] or factory_interface_matches(name, got)) or overlay_matches(name,got):states.add('after')
    elif got==entry['before']:states.add('before')
    else:raise RuntimeError('Unexpected r85 source: '+name)
assert len(states)==1,'Partial r85 source patch'
if '--check' in sys.argv:
    assert states=={'after'}
elif states=={'before'}:
    subprocess.run(['patch','--batch','--forward','-p1','-i',str(patch)],cwd=root,check=True)
for name,entry in receipt['files'].items():
    got=hashlib.sha256((root/name).read_bytes()).hexdigest()
    assert (got==entry['after'] or factory_interface_matches(name, got)) or overlay_matches(name,got),name
print('Verified '+receipt['revision']+' patch and all source headers')

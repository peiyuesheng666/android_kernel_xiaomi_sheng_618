#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

project=Path(os.environ['PROJECT_ROOT']).resolve()
root=Path(os.environ['BUILD_ROOT']).resolve()
receipt=json.loads((project/'provenance/repair-r85.json').read_text())
patch=project/receipt['patch']
assert hashlib.sha256(patch.read_bytes()).hexdigest()==receipt['patch_sha256']
states=set()
for name,entry in receipt['files'].items():
    path=root/name
    got=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    if got==entry['after']:states.add('after')
    elif got==entry['before']:states.add('before')
    else:raise RuntimeError('Unexpected r85 source: '+name)
assert len(states)==1,'Partial r85 source patch'
if '--check' in sys.argv:
    assert states=={'after'}
elif states=={'before'}:
    subprocess.run(['patch','--batch','--forward','-p1','-i',str(patch)],cwd=root,check=True)
for name,entry in receipt['files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==entry['after'],name
print('Verified '+receipt['revision']+' patch and all source headers')

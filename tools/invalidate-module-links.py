#!/usr/bin/env python3
import json
import os
from pathlib import Path
project=Path(os.environ['PROJECT_ROOT']).resolve()
k618=Path(os.environ['K618']).resolve()
output=k618/'out-gki'
mapping=json.loads((project/'profiles/module-sources.json').read_text())
assert len(mapping)==345
count=0
for name,source in mapping.items():
    path=(output/source[4:] if source.startswith('out/') else k618/source)
    resolved=path.resolve()
    assert resolved.is_relative_to(k618) and resolved.suffix=='.ko',path
    if path.exists():
        path.unlink();count+=1
print('Invalidated %d mapped module links; object files retained, BTF regenerated' % count,flush=True)

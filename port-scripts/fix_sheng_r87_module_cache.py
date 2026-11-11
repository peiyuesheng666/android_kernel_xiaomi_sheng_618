"""Regenerate every mapped .ko's split BTF against this module-build kernel."""
from pathlib import Path
import shutil
w=Path(__file__).resolve().parents[1]
p=Path('/root/sheng-618-repair-r87-project')
tool=p/'tools/invalidate-module-links.py'
tool.write_text('''#!/usr/bin/env python3
import json
import os
from pathlib import Path
project=Path(os.environ['PROJECT_ROOT']).resolve()
k618=Path(os.environ['K618']).resolve()
output=k618/'out-gki'
mapping=json.loads((project/'profiles/module-sources.json').read_text())
assert len(mapping)==344
count=0
for name,source in mapping.items():
    path=(output/source[4:] if source.startswith('out/') else k618/source)
    resolved=path.resolve()
    assert resolved.is_relative_to(k618) and resolved.suffix=='.ko',path
    if path.exists():
        path.unlink();count+=1
print('Invalidated %d mapped module links; object files retained, BTF regenerated' % count,flush=True)
''')
path=p/'buildmodules.sh';s=path.read_text()
anchor='run gki-modules "${make_cmd[@]}" modules'
assert s.count(anchor)==1
s=s.replace(anchor,'''# Split BTF is tied to vmlinux even when module object files are unchanged.
# Regenerate the final .ko links before extracting this run's kernel BTF base.
"$PYTHON" "$PROJECT_ROOT/tools/invalidate-module-links.py"
'''+anchor)
path.write_text(s)
shutil.copyfile(w/'scripts/fix_sheng_r87_module_cache.py',p/'port-scripts/fix_sheng_r87_module_cache.py')
print('r87 buildmodules now relinks all mapped modules against fresh BTF')

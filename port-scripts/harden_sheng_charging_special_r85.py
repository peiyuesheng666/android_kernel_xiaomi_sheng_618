#!/usr/bin/env python3
"""Harden factory polling and regenerate the complete r76-to-r85 receipt."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

workspace = Path(__file__).resolve().parents[1]
project = Path('/root/sheng-618-repair-r85-project')
build = Path('/root/sheng-618-repair-r85-build')
baseline = Path('/root/sheng-618-pen-release-build')
receipt_path = project/'provenance/repair-r85.json'
receipt = json.loads(receipt_path.read_text())
name = 'k618/soc/drivers/power/supply/sheng_charging_special.h'
path = build/name
source = path.read_text()
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(path.read_bytes()) == receipt['files'][name]['after']
anchor = '''        if (rc < 0)
            goto out;
        if (strncmp(value, "updating", 8))'''
replacement = '''        if (rc < 0)
            goto out;
        if (!sheng_charging_live(bcdev)) {
            rc = -ENOTCONN;
            goto out;
        }
        if (rc == 0 || value[0] == '\\0' || value[0] == '\\n') {
            rc = -ENODATA;
            goto out;
        }
        if (strncmp(value, "updating", 8))'''
if replacement not in source:
    assert source.count(anchor) == 1
    path.write_text(source.replace(anchor, replacement))
receipt['files'][name]['after'] = sha(path.read_bytes())
receipt['special_abi_notes']['factory_rejects_empty_or_disconnected_reply'] = True
patch = ''
for relative, state in receipt['files'].items():
    old = baseline/relative
    assert (sha(old.read_bytes()) if old.exists() else None) == state['before'], relative
    before = old.read_text() if old.exists() else ''
    after = (build/relative).read_text()
    patch += ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                     fromfile='a/'+relative if before else '/dev/null', tofile='b/'+relative))
(project/receipt['patch']).write_text(patch)
receipt['patch_sha256'] = sha(patch.encode())
receipt_path.write_text(json.dumps(receipt, indent=2)+'\n')
(workspace/'reports/kernel618-repair-r85-stage.json').write_text(json.dumps(receipt, indent=2)+'\n')
for script in ('harden_sheng_charging_special_r85.py', 'test_sheng_charging_special_r85.py'):
    shutil.copyfile(workspace/'scripts'/script, project/'port-scripts'/script)
print('Updated factory polling and verified complete baseline hashes', flush=True)

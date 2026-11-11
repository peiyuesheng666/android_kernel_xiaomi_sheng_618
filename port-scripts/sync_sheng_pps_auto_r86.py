#!/usr/bin/env python3
"""Update exactly tracked r86 headers and regenerate its r76-based patch."""
from pathlib import Path
import difflib
import hashlib
import json
import re
import shutil

workspace=Path(__file__).resolve().parents[1]
project=Path('/root/sheng-618-repair-r86-project')
build=Path('/root/sheng-618-repair-r86-build')
baseline=Path('/root/sheng-618-pen-release-build')
receipt_path=project/'provenance/repair-r85.json'
receipt=json.loads(receipt_path.read_text())
receipt['pps_auto_policy']['stable_grace_seconds']=0
receipt['pps_auto_policy']['immediate_after_confirmed_recognition']=True
receipt['pps_auto_policy'].pop('power_and_adapter_id_guard_only_when_svid_unknown',None)
receipt['pps_auto_policy']['native_adapter_id_nonzero_skipped']=True
receipt['pps_auto_policy']['stale_xiaomi_svid_with_zero_id_and_sub110w_eligible']=True
receipt['pps_auto_policy']['sink_ready_property_id']=21
receipt['pps_auto_policy']['sink_ready_value']=31
sha=lambda data:hashlib.sha256(data).hexdigest()
main='k618/soc/drivers/power/supply/qti_battery_charger.c'
path=build/main;source=path.read_text()
assert sha(path.read_bytes())==receipt['files'][main]['after']
anchor='\tcase BC_XM_STATUS_GET:\n\t\tschedule_delayed_work(&bcdev->xm_prop_change_work, 0);'
replacement=anchor+'\n\t\tsheng_pps_kick(bcdev);'
if replacement not in source:
    assert source.count(anchor)==1
    path.write_text(source.replace(anchor,replacement))
    receipt['files'][main]['after']=sha(path.read_bytes())
source=path.read_text()
manual=re.search(r'static ssize_t pd_verifed_store\([^{}]*\)\s*\{.*?^\}',source,re.M|re.S)[0]
fixed=manual.replace('    return rc < 0 ? rc : count;', '    if (rc < 0)\n        return rc;\n    return count;')
if fixed!=manual:
    path.write_text(source.replace(manual,fixed))
    receipt['files'][main]['after']=sha(path.read_bytes())
for header in ('sheng_pps_policy.h','sheng_pps_auto_verify.h'):
    name='k618/soc/drivers/power/supply/'+header;target=build/name
    assert sha(target.read_bytes())==receipt['files'][name]['after']
    shutil.copyfile(workspace/'scripts/r86'/header,target)
    receipt['files'][name]['after']=sha(target.read_bytes())
patch=''
for name,state in receipt['files'].items():
    old=baseline/name;assert (sha(old.read_bytes()) if old.exists() else None)==state['before'],name
    before=old.read_text() if old.exists() else '';after=(build/name).read_text()
    patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
        fromfile='a/'+name if before else '/dev/null',tofile='b/'+name))
(project/receipt['patch']).write_text(patch);receipt['patch_sha256']=sha(patch.encode())
receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
(workspace/'reports/kernel618-repair-r86-stage.json').write_text(json.dumps(receipt,indent=2)+'\n')
for name in ('sync_sheng_pps_auto_r86.py','test_sheng_pps_auto_r86.py'):
    if (workspace/'scripts'/name).exists():shutil.copyfile(workspace/'scripts'/name,project/'port-scripts'/name)
print('Synced tracked PPS headers and r86 patch hashes',flush=True)

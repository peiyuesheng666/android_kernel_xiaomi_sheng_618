"""Preserve r86 delivery; reuse its mutable native build directory for r87."""
from pathlib import Path
import difflib
import hashlib
import json
import shutil

w=Path(__file__).resolve().parents[1]
old=Path('/root/sheng-618-repair-r86-project')
p=Path('/root/sheng-618-repair-r87-project')
b=Path('/root/sheng-618-repair-r86-build')
base=Path('/root/sheng-618-pen-release-build')
assert not p.exists()
assert json.loads((w/'artifacts/sheng-6.18-repair-r86/package-validation.json').read_text())['archive_readback_verified']
shutil.copytree(old,p,symlinks=True,ignore=shutil.ignore_patterns('.git','dist','logs','__pycache__','*.pyc'))
env=p/'scripts/project-env.sh';env.write_text(env.read_text().replace('TAG="${TAG:-repair-r86}"','TAG="${TAG:-repair-r87}"'))
r=json.loads((p/'provenance/repair-r85.json').read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()
for name,h in r['files'].items():assert sha((b/name).read_bytes())==h['after'],name
folder=b/'k618/soc/drivers/power/supply'
policy=(w/'scripts/r86/sheng_pps_policy.h').read_text()
policy=policy.replace('input_suspended;', 'input_suspended, verifying;').replace('connected, inhibit','connected')
policy=policy.replace('<=100 W','<100 W').replace('>= 110','>= 100')
policy=policy.replace('if (!s->ready ||','if (s->verifying || !s->ready ||').replace('p->inhibit || ','')
(folder/'sheng_pps_policy.h').write_text(policy)
worker=(w/'scripts/r86/sheng_pps_auto_verify.h').read_text()
worker=worker.replace('Verify eligible third-party PPS after native discovery; replug after changing',
                      'Maintain eligible third-party PPS after native discovery; N disables automatic writes')
anchor='    /* Shipping current_state_show maps firmware state 31 to SNK_Ready. */'
worker=worker.replace(anchor,'''    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_VERIFY_PROCESS, &match);
    if (rc < 0)
        return rc;
    s->verifying = match != 0;
'''+anchor)
worker=worker.replace('    unsigned long retry_delay = 0;','    unsigned long retry_delay = 0;')
worker=worker.replace('    if (action != SHENG_PPS_UNLOCK)\n        goto out;', '''    /* Only attached PPS is monitored; already verified samples cost three reads.
     * Events and stores kick immediately. The five-second fallback catches
     * firmware-only clears; it is not a recognition grace period. */
    retry = sample.online && sample.pps && bcdev->sheng_pps.attempts < 3;
    retry_delay = 5 * HZ;
    if (action != SHENG_PPS_UNLOCK)
        goto out;''')
worker=worker.replace('        retry = action == SHENG_PPS_UNLOCK;',
                      '        retry = sample.online && sample.pps && bcdev->sheng_pps.attempts < 3;\n        retry_delay = 0;')
worker=worker.replace('        retry = true;\n        goto out;', '        retry = true;\n        retry_delay = 0;\n        goto out;')
worker=worker.replace('    ++bcdev->sheng_pps.attempts;\n    rc = write_property_id', '    rc = write_property_id')
worker=worker.replace('    changed = true;', '    bcdev->sheng_pps.attempts = 0;\n    changed = true;')
worker=worker.replace('error:\n    ++bcdev->sheng_pps.attempts;\nwrite_error:',
                      'error:\nwrite_error:\n    if (bcdev->sheng_pps.attempts < 3)\n        ++bcdev->sheng_pps.attempts;')
worker=worker.replace('queue_delayed_work(system_freezable_wq, &bcdev->sheng_pps_work, 0);',
                      'mod_delayed_work(system_freezable_wq, &bcdev->sheng_pps_work, 0);')
(folder/'sheng_pps_auto_verify.h').write_text(worker)
main=folder/'qti_battery_charger.c';s=main.read_text()
oldblock='''    /* Explicit zero while connected wins until the next observed disconnect. */
    if (rc >= 0 && !val && bcdev->sheng_pps.connected)
        bcdev->sheng_pps.inhibit = true;'''
assert s.count(oldblock)==1
s=s.replace(oldblock,'''    /* batterysecret also writes zero on third-party auth failure. Automatic
     * mode re-evaluates the live source instead of inhibiting the connection. */''')
start=s.index('static ssize_t pd_verifed_store(');end=s.index('\nstatic ssize_t pd_verifed_show',start)
part=s[start:end].replace('    return count;', '    sheng_pps_kick(bcdev);\n    return count;')
s=s[:start]+part+s[end:]
start=s.index('static ssize_t verify_process_store(');end=s.index('\nstatic ssize_t verify_process_show',start)
part=s[start:end]
part=part.replace('\trc = write_property_id', '\tmutex_lock(&bcdev->sheng_pps_lock);\n\tatomic_inc(&bcdev->sheng_pps_epoch);\n\trc = write_property_id')
part=part.replace('\tif (rc < 0)', '\tmutex_unlock(&bcdev->sheng_pps_lock);\n\tif (rc < 0)')
part=part.replace('\treturn count;', '\tsheng_pps_kick(bcdev);\n\treturn count;')
s=s[:start]+part+s[end:];main.write_text(s)
r['revision']='repair-r87';r['patch']='patches/sheng-repair-r87.patch'
r['project']=str(p);r['build']=str(b)
r['reused_mutable_build_cache']=True
policy=r['pps_auto_policy']
for key in ['explicit_zero_inhibits_until_disconnect','max_attempts_per_connection','stale_xiaomi_svid_with_zero_id_and_sub110w_eligible']:policy.pop(key,None)
policy.update(native_power_threshold_watts=100,verify_process_property_id=12,
              waits_for_native_verification_end=True,sysfs_zero_kicks_immediate_recheck=True,
              successful_writes_reset_failure_budget=True,max_consecutive_failures=3,
              attached_pps_fallback_poll_seconds=5,stale_xiaomi_svid_zero_id_sub100w_eligible=True,
              evidence='batterysecret writes verify_process 1 then 0 and pd_verifed 0; private kprobe trace 20261111-203944')
patch=''
for name,h in r['files'].items():
    h['after']=sha((b/name).read_bytes())
    path=base/name;assert (sha(path.read_bytes()) if path.exists() else None)==h['before']
    before=path.read_text() if path.exists() else '';after=(b/name).read_text()
    patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+name if before else '/dev/null',tofile='b/'+name))
(p/r['patch']).write_text(patch);r['patch_sha256']=sha(patch.encode())
(p/'provenance/repair-r85.json').write_text(json.dumps(r,indent=2)+'\n')
(w/'reports/kernel618-repair-r87-stage.json').write_text(json.dumps(r,indent=2)+'\n')
(w/'scripts/r87').mkdir(exist_ok=True)
for name in ['sheng_pps_policy.h','sheng_pps_auto_verify.h']:shutil.copyfile(folder/name,w/'scripts/r87'/name)
print('r87 source staged with preserved r86 artifacts; reused native build cache',flush=True)

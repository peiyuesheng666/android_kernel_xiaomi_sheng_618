#!/usr/bin/env python3
"""Add delayed third-party PPS verification, preserving native Xiaomi discovery."""
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
relative='k618/soc/drivers/power/supply/qti_battery_charger.c'
path=build/relative;source=path.read_text()
sha=lambda data:hashlib.sha256(data).hexdigest()
assert sha(path.read_bytes())==receipt['files'][relative]['after']
assert 'sheng_pps_policy.h' not in source
def replace(old,new):
    global source
    assert source.count(old)==1,old
    source=source.replace(old,new)
def amend_function(name,amend):
    global source
    start=source.index('static ',source.index(name)-32)
    brace=source.index('{',source.index(name));level=1;end=brace+1
    while level:
        level+=(source[end]=='{')-(source[end]=='}');end+=1
    function=source[start:end]
    changed=amend(function)
    assert changed!=function,name
    source=source[:start]+changed+source[end:]
replace('#include <linux/mutex.h>','#include <linux/mutex.h>\n#include <linux/jiffies.h>\n#include <linux/workqueue.h>')
replace('struct battery_chg_dev {','#include "sheng_pps_policy.h"\n\nstruct battery_chg_dev {')
replace('\tstruct work_struct\t\tusb_type_work;', '''\tstruct work_struct\t\tusb_type_work;
\tstruct delayed_work sheng_pps_work;
\tstruct mutex sheng_pps_lock;
\tstruct sheng_pps_policy sheng_pps;
\tatomic_t sheng_pps_epoch, sheng_pps_reset;
\tbool sheng_pps_stopping;''')
replace('static void battery_chg_update_usb_type_work(',
    '#include "sheng_pps_auto_verify.h"\n\nstatic void battery_chg_update_usb_type_work(')
amend_function('battery_chg_update_usb_type_work',lambda f:f[:-1]+'\tsheng_pps_kick(bcdev);\n}')
amend_function('battery_chg_update_usb_type_work',lambda f:f.replace('''\trc = read_property_id(bcdev, pst, USB_ADAP_TYPE);''','''\tif (READ_ONCE(bcdev->sheng_pps_stopping))
\t\treturn;
\trc = read_property_id(bcdev, pst, USB_ADAP_TYPE);'''))
amend_function('battery_chg_subsys_up_work',lambda f:f[:-1]+'\tschedule_work(&bcdev->usb_type_work);\n}')
replace('\tatomic_set(&bcdev->state, state);','''\tatomic_inc(&bcdev->sheng_pps_epoch);
\tif (state == PMIC_GLINK_STATE_DOWN)
\t\tatomic_set(&bcdev->sheng_pps_reset, 1);
\tatomic_set(&bcdev->state, state);''')
replace('''\tcase BC_USB_STATUS_GET:
\t\tpst = &bcdev->psy_list[PSY_TYPE_USB];
\t\tschedule_work(&bcdev->usb_type_work);''','''\tcase BC_USB_STATUS_GET:
\t\tpst = &bcdev->psy_list[PSY_TYPE_USB];
\t\tatomic_inc(&bcdev->sheng_pps_epoch);
\t\tschedule_work(&bcdev->usb_type_work);''')
replace('\tINIT_WORK(&bcdev->usb_type_work, battery_chg_update_usb_type_work);','''\tINIT_WORK(&bcdev->usb_type_work, battery_chg_update_usb_type_work);
\tINIT_DELAYED_WORK(&bcdev->sheng_pps_work, sheng_pps_auto_work);
\tmutex_init(&bcdev->sheng_pps_lock);
\tatomic_set(&bcdev->sheng_pps_epoch, 0);
\tatomic_set(&bcdev->sheng_pps_reset, 0);''')
old=re.search(r'static ssize_t pd_verifed_store\([^{}]*\)\s*\{.*?^\}',source,re.S|re.M)[0]
new='''static ssize_t pd_verifed_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    bool val;
    int rc;
    if (kstrtobool(buf, &val))
        return -EINVAL;
    mutex_lock(&bcdev->sheng_pps_lock);
    rc = sheng_pps_live(bcdev) ?
        write_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM], XM_PROP_PD_VERIFED, val) :
        -ENOTCONN;
    if (rc >= 0 && !sheng_pps_live(bcdev))
        rc = -ENOTCONN;
    /* Explicit zero while connected wins until the next observed disconnect. */
    if (rc >= 0 && !val && bcdev->sheng_pps.connected)
        bcdev->sheng_pps.inhibit = true;
    mutex_unlock(&bcdev->sheng_pps_lock);
    if (rc < 0)
        return rc;
    return count;
}'''
replace(old,new)
replace('''error:
\tcancel_work_sync(&bcdev->subsys_up_work);''','''error:
\tWRITE_ONCE(bcdev->sheng_pps_stopping, true);
\tcancel_work_sync(&bcdev->subsys_up_work);
\tcancel_work_sync(&bcdev->usb_type_work);
\tcancel_delayed_work_sync(&bcdev->sheng_pps_work);''')
replace('''\tpmic_glink_unregister_client(bcdev->client);
\tunregister_reboot_notifier''','''\tpmic_glink_unregister_client(bcdev->client);
\tcancel_work_sync(&bcdev->usb_type_work);
\tcancel_delayed_work_sync(&bcdev->sheng_pps_work);
\tunregister_reboot_notifier''')
amend_function('battery_chg_remove',lambda f:f.replace('\tint rc;','''\tint rc;

\tWRITE_ONCE(bcdev->sheng_pps_stopping, true);
\tcancel_work_sync(&bcdev->subsys_up_work);
\tcancel_work_sync(&bcdev->usb_type_work);
\tcancel_delayed_work_sync(&bcdev->sheng_pps_work);''').replace(
    '\tcancel_work_sync(&bcdev->sheng_pen_work);',
    '\tcancel_work_sync(&bcdev->usb_type_work);\n\tcancel_delayed_work_sync(&bcdev->sheng_pps_work);\n\tcancel_work_sync(&bcdev->sheng_pen_work);'))
path.write_text(source);receipt['files'][relative]['after']=sha(path.read_bytes())
for header in ('sheng_pps_policy.h','sheng_pps_auto_verify.h'):
    name='k618/soc/drivers/power/supply/'+header;target=build/name
    assert not target.exists();shutil.copyfile(workspace/'scripts/r86'/header,target)
    receipt['files'][name]=dict(before=None,after=sha(target.read_bytes()))
receipt.update(revision='repair-r86',project=str(project),build=str(build),
    patch='patches/sheng-repair-r86.patch',default_charging_writes_added=True,
    pps_auto_policy=dict(default_enabled=True,only_real_online_pps=True,stable_grace_seconds=20,
        preserves_existing_one=True,native_svid=0x2717,native_power_threshold_watts=110,
        ambiguous_nonzero_adapter_id_skipped=True,huawei_svid=0x12d1,
        authenticated_dual_battery_and_good_health_required=True,max_attempts_per_connection=3,
        explicit_zero_inhibits_until_disconnect=True,glink_readback_required=True,
        writes_current_or_thermal_limits=False,hardware_verified=False))
patch=''
for name,state in receipt['files'].items():
    old=baseline/name;assert (sha(old.read_bytes()) if old.exists() else None)==state['before'],name
    before=old.read_text() if old.exists() else '';after=(build/name).read_text()
    patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
        fromfile='a/'+name if before else '/dev/null',tofile='b/'+name))
(project/receipt['patch']).write_text(patch);receipt['patch_sha256']=sha(patch.encode())
receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
(workspace/'reports/kernel618-repair-r86-stage.json').write_text(json.dumps(receipt,indent=2)+'\n')
# Same inherited hash gates now read the r86 combined receipt in this isolated project.
path=project/'scripts/apply-repair-r85.py';text=path.read_text()
text=text.replace("print('Verified shipping r85 charging patch and all new source headers')",
    "print('Verified '+receipt['revision']+' patch and all source headers')")
path.write_text(text)
path=project/'scripts/verify.py';text=path.read_text().replace("'repair_r85': repair_fix","'repair_r86': repair_fix")
text=text.replace('pinned baseline cache plus inherited and repair-r85 patches',
    'pinned r76 baseline cache plus inherited and combined repair-r86 patches')
path.write_text(text)
mapping=json.loads((project/'profiles/module-sources.json').read_text());assert len(mapping)==344
for name in mapping.values():
    target=build/'k618'/('out-gki/'+name[4:] if name.startswith('out/') else name)
    assert target.resolve().is_relative_to(build.resolve()) and target.suffix=='.ko'
    if target.exists():target.unlink()
shutil.copyfile(workspace/'scripts/stage_sheng_pps_auto_r86.py',project/'port-scripts/stage_sheng_pps_auto_r86.py')
print(json.dumps(dict(revision='repair-r86',source_sha256=receipt['files'][relative]['after'],
                      policy=receipt['pps_auto_policy'])),flush=True)

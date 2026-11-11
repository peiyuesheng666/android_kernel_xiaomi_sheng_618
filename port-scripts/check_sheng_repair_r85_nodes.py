#!/usr/bin/env python3
"""Read all restored interfaces, preserving firmware errors and physical limits."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

workspace=Path(__file__).resolve().parents[1]
delivery=workspace/'artifacts/sheng-6.18-repair-r85'
receipt=json.loads((delivery/'repair-r85.json').read_text())
adb=[str(workspace/'tools/platform-tools/adb.exe'),'-s','192.168.1.14:5555']
folder=workspace/'logs'/('r85-nodes-'+time.strftime('%Y%m%d-%H%M%S'));folder.mkdir()
def shell(command,root=False,timeout=20,check=True):
    if root:command="su -c '"+command.replace("'","'\"'\"'")+"'"
    result=subprocess.run(adb+['shell',command],capture_output=True,timeout=timeout)
    if check and result.returncode:raise RuntimeError((result.stdout+result.stderr).decode(errors='replace'))
    return result
def read(command,root=False):return shell(command,root).stdout.decode(errors='replace').strip()
assert read('getprop ro.serialno')=='603ac302'
expected=json.loads((delivery/'package-validation.json').read_text())['boot_sha256']
assert read('sha256sum /dev/block/by-name/boot_a',True).split()[0]==expected
report=dict(serial='603ac302',boot_sha256=expected,boot_id=read('cat /proc/sys/kernel/random/boot_id'),
    restored=[],writes_performed=False,semantic_hardware_acceptance=False)
def save():
    (folder/'nodes.json').write_text(json.dumps(report,indent=2)+'\n')
    (workspace/'reports/kernel618-repair-r85-nodes.json').write_text(json.dumps(report,indent=2)+'\n')
for command,name in [('ls -l /sys/class/qcom-battery/','attributes.txt'),
                     ('cat /sys/class/power_supply/usb/uevent /sys/class/power_supply/battery/uevent','power-supplies.txt'),
                     ('cat /proc/modules','modules.txt')]:
    (folder/name).write_bytes(shell(command,True).stdout)
names=['charging_suspend_battery']+[row['node'] for row in receipt['restored_scalar_nodes']]+receipt['restored_special_nodes']
assert len(names)==len(set(names))==57
for i,name in enumerate(names):
    path='/sys/class/qcom-battery/'+name
    exists=read('test -e '+path+' && echo present',True)=='present'
    result=shell('timeout 7 cat '+path,True,timeout=12,check=False)
    report['restored'].append(dict(node=name,exists=exists,returncode=result.returncode,
        stdout=result.stdout.decode(errors='replace').strip(),stderr=result.stderr.decode(errors='replace').strip()))
    save()
    if i%10==0:print(json.dumps(dict(stage='reading',completed=i+1,total=57)),flush=True)
report['all_57_present']=all(row['exists'] for row in report['restored'])
report['successful_reads']=sum(row['returncode']==0 for row in report['restored'])
report['failed_reads']=[row['node'] for row in report['restored'] if row['returncode']!=0]
report['pen_hold_ms']=read('cat /sys/module/nt36532_touch/parameters/sheng_pen_contact_hold_ms')
report['authentic']=read('cat /sys/class/qcom-battery/authentic',True)
report['slave_authentic']=read('cat /sys/class/qcom-battery/slave_authentic',True)
(folder/'dmesg.txt').write_bytes(shell('dmesg',True).stdout)
report['complete']=True;save()
assert report['all_57_present']
print(json.dumps({k:v for k,v in report.items() if k!='restored'}),flush=True)

#!/usr/bin/env python3
"""Temporarily toggle the original battery-suspend property on real external power."""
from pathlib import Path
import json
import subprocess
import time

workspace=Path(__file__).resolve().parents[1]
adb=[str(workspace/'tools/platform-tools/adb.exe'),'-s','192.168.1.14:5555']
folder=workspace/'logs'/('r86-bypass-'+time.strftime('%Y%m%d-%H%M%S'));folder.mkdir()
def call(command,root=False):
    if root:command="su -c '"+command.replace("'","'\"'\"'")+"'"
    result=subprocess.run(adb+['shell',command],capture_output=True,timeout=20)
    assert result.returncode==0,(command,result.stderr.decode(errors='replace'))
    return result.stdout.decode(errors='replace').strip()
def node(name):return call('cat /sys/class/qcom-battery/'+name,True)
def uevent(name):return dict(line.split('=',1) for line in call('cat /sys/class/power_supply/'+name+'/uevent').splitlines() if '=' in line)
def sample(phase):
    assert call('getprop ro.serialno')=='603ac302'
    usb=uevent('usb');battery=uevent('battery')
    return dict(phase=phase,time=time.time(),usb=usb,battery=battery,
        input_watts=int(usb['POWER_SUPPLY_VOLTAGE_NOW'])*int(usb['POWER_SUPPLY_CURRENT_NOW'])/1e12,
        nodes={name:node(name) for name in ('charging_suspend_battery','fg1_ibatt','fg2_ibatt','input_suspend','pd_verifed','real_type')})
report=dict(serial='603ac302',samples=[],writes=['charging_suspend_battery'],original_restored=False,
            physical_bypass_verified=False)
def save():
    (folder/'probe.json').write_text(json.dumps(report,indent=2)+'\n')
    (workspace/'reports/kernel618-repair-r86-bypass.json').write_text(json.dumps(report,indent=2)+'\n')
assert call('getprop ro.serialno')=='603ac302'
expected=json.loads((workspace/'artifacts/sheng-6.18-repair-r86/package-validation.json').read_text())['boot_sha256']
assert call('sha256sum /dev/block/by-name/boot_a',True).split()[0]==expected
first=sample('preflight');report['samples'].append(first);save()
assert first['usb']['POWER_SUPPLY_ONLINE']=='1','External power required; no bypass write performed'
assert node('authentic')==node('slave_authentic')=='1'
assert first['battery']['POWER_SUPPLY_HEALTH']=='Good'
original=first['nodes']['charging_suspend_battery'];assert original in ('0','1')
report['original']=original
def set_value(value):
    call('echo '+value+' > /sys/class/qcom-battery/charging_suspend_battery',True)
    assert node('charging_suspend_battery')==value
try:
    if original=='1':set_value('0')
    for phase,value in (('charging_baseline','0'),('bypass_enabled','1'),('charging_restored','0')):
        set_value(value)
        for i in range(3):
            time.sleep(5)
            row=sample(phase);report['samples'].append(row);save()
            assert row['usb']['POWER_SUPPLY_ONLINE']=='1','Power removed during test'
            assert row['nodes']['charging_suspend_battery']==value
            assert row['nodes']['input_suspend']==first['nodes']['input_suspend']
            print(json.dumps(dict(phase=phase,input_watts=row['input_watts'],
                  battery_current=row['battery']['POWER_SUPPLY_CURRENT_NOW'],
                  fg1_ibatt=row['nodes']['fg1_ibatt'],fg2_ibatt=row['nodes']['fg2_ibatt'])),flush=True)
finally:
    set_value(original);report['original_restored']=True;save()
report['toggle_and_restore_passed']=True
report['needs_interpretation']='Confirm both battery currents stop charging while USB powers the tablet; unplug test remains separate'
report['complete']=True;save()
print(json.dumps(dict(stage='complete',folder=str(folder),original_restored=True)),flush=True)

#!/usr/bin/env python3
"""Measure the authorized PD verification override on a real PPS connection."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time

workspace=Path(__file__).resolve().parents[1]
adb=[str(workspace/'tools/platform-tools/adb.exe'),'-s','192.168.1.14:5555']
folder=workspace/'logs'/('r85-pps-'+time.strftime('%Y%m%d-%H%M%S'))
folder.mkdir()
def call(command,root=False):
    if root:command="su -c '"+command.replace("'","'\"'\"'")+"'"
    p=subprocess.run(adb+['shell',command],capture_output=True,timeout=25)
    assert p.returncode==0,(command,p.stderr.decode(errors='replace'))
    return p.stdout.decode(errors='replace').strip()
def prop(name):return call('cat /sys/class/qcom-battery/'+name,True)
def parse_uevent(value):
    return dict(line.split('=',1) for line in value.splitlines() if '=' in line)
nodes='pd_verifed real_type apdo_max power_max adapter_id adapter_svid fastchg_mode authentic slave_authentic bap_match input_suspend restrict_chg restrict_cur pdo2 current_state bq2597x_bus_voltage bq2597x_bus_current bq2597x_slave_bus_current'.split()
def snapshot():
    assert call('getprop ro.serialno')=='603ac302'
    usb=parse_uevent(call('cat /sys/class/power_supply/usb/uevent'))
    battery=parse_uevent(call('cat /sys/class/power_supply/battery/uevent'))
    watts=int(usb['POWER_SUPPLY_VOLTAGE_NOW'])*int(usb['POWER_SUPPLY_CURRENT_NOW'])/1e12
    values={name:prop(name) for name in nodes}
    cp_estimate=int(values['bq2597x_bus_voltage'])*(int(values['bq2597x_bus_current'])+int(values['bq2597x_slave_bus_current']))/1e6
    return dict(time_utc=datetime.now(timezone.utc).isoformat(),usb=usb,battery=battery,
                input_watts=watts,nodes=values,charge_pump_input_watts_estimate=cp_estimate,
                power_measurement_note='USB current reporting needs cross-check; CP estimate assumes shared parallel input bus, not an external power-meter measurement')
report=dict(serial='603ac302',purpose='temporary pd_verifed=1 test on real standard PPS',samples=[],
            persistent_changes=False,current_or_thermal_limits_written=False,boot_written=False,
            pd_verifed_write_performed=False)
def save():
    (folder/'probe.json').write_text(json.dumps(report,indent=2)+'\n')
assert call('getprop ro.serialno')=='603ac302'
report['boot_id']=call('cat /proc/sys/kernel/random/boot_id')
first=snapshot();report['samples'].append(dict(phase='preflight',**first));save()
assert first['usb']['POWER_SUPPLY_ONLINE']=='1','Connect the standard PPS charger before this probe'
assert 'PPS' in first['nodes']['real_type'].upper(),first['nodes']['real_type']
assert first['nodes']['authentic']==first['nodes']['slave_authentic']=='1','Battery authentication is not ready'
assert first['battery']['POWER_SUPPLY_HEALTH']=='Good'
original=first['nodes']['pd_verifed'];assert original in ('0','1')
report['original_pd_verifed']=original
before_log=call('dmesg',True)
(folder/'dmesg-before.txt').write_text(before_log)
last=max(float(v) for v in re.findall(r'^\[\s*([0-9.]+)\]',before_log,re.M))
changed=False
try:
    for i in range(2):
        time.sleep(10);row=snapshot();report['samples'].append(dict(phase='before',**row));save()
        if row['usb']['POWER_SUPPLY_ONLINE']!='1' or 'PPS' not in row['nodes']['real_type'].upper():
            report['stopped']='PPS connection disconnected during observation';save()
            print(json.dumps(dict(stage='disconnected',folder=str(folder),write_performed=False)),flush=True)
            raise SystemExit(0)
    report['already_verified_on_connection']=original=='1'
    report['override_effect_testable']=original=='0'
    if original=='0':
        call('echo 1 > /sys/class/qcom-battery/pd_verifed',True);changed=True
        report['pd_verifed_write_performed']=True
    report['write_one_readback']=prop('pd_verifed');save()
    assert report['write_one_readback']=='1','Firmware did not acknowledge pd_verifed=1'
    print(json.dumps(dict(stage='pd_verifed_one_acknowledged',already_one=original=='1',
                         write_performed=changed,folder=str(folder))),flush=True)
    for i in range(4):
        time.sleep(10)
        row=snapshot();report['samples'].append(dict(phase='after',**row));save()
        if row['usb']['POWER_SUPPLY_ONLINE']!='1':
            report['stopped']='PPS connection disconnected during sampling';save()
            raise SystemExit(0)
        print(json.dumps(dict(phase='after',usb_reported_watts=row['input_watts'],cp_estimate_watts=row['charge_pump_input_watts_estimate'],pd_verifed=row['nodes']['pd_verifed'],
                             capacity=row['battery']['POWER_SUPPLY_CAPACITY'],temperature=row['battery']['POWER_SUPPLY_TEMP'])),flush=True)
finally:
    if changed:
        call('echo '+original+' > /sys/class/qcom-battery/pd_verifed',True)
        report['restored_pd_verifed']=prop('pd_verifed');save()
        assert report['restored_pd_verifed']==original
after_log=call('dmesg',True)
(folder/'dmesg-after.txt').write_text(after_log)
new=[]
for line in after_log.splitlines():
    m=re.match(r'^\[\s*([0-9.]+)\]',line)
    if m and float(m[1])>last and re.search(r'BATTERY_CHG|charger|PdAuth',line,re.I):new.append(line)
(folder/'new-charging-dmesg.txt').write_text('\n'.join(new)+'\n')
report['boot_unchanged']=call('cat /proc/sys/kernel/random/boot_id')==report['boot_id']
report['complete']=True;save()
print(json.dumps(dict(stage='complete',folder=str(folder))),flush=True)

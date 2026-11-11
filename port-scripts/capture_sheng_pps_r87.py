"""Read flag/capability timing on the hash-verified r87 kernel; no auth payloads."""
from pathlib import Path
import argparse
import json
import subprocess
import time
w=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--label',required=True,choices=['huawei','xiaomi','unplug','snapshot'])
parser.add_argument('--samples',type=int,default=20)
parser.add_argument('--interval',type=float,default=1)
a=parser.parse_args();assert 1<=a.samples<=90 and 0<=a.interval<=10
adb=[str(w/'tools/platform-tools/adb.exe'),'-s','192.168.1.14:5555']
def read(cmd,root=True):
    if root:cmd="su -c '"+cmd.replace("'","'\"'\"'")+"'"
    r=subprocess.run(adb+['shell',cmd],capture_output=True,timeout=20)
    assert not r.returncode,(cmd,r.stderr.decode(errors='replace'))
    return r.stdout.decode(errors='replace').strip()
assert read('getprop ro.serialno',False)=='603ac302'
expected=json.loads((w/'artifacts/sheng-6.18-repair-r87/package-validation.json').read_text())['boot_sha256']
assert read('sha256sum /dev/block/by-name/boot_a').split()[0]==expected
folder=w/'logs'/('pps-r87-'+a.label+'-'+time.strftime('%Y%m%d-%H%M%S'));folder.mkdir()
report=dict(serial='603ac302',label=a.label,read_only=True,boot_sha256=expected,
            boot_id=read('cat /proc/sys/kernel/random/boot_id'),samples=[])
names=['pd_verifed','verify_process','adapter_svid','adapter_id','apdo_max','power_max',
       'current_state','real_type','quick_charge_type','charging_suspend_battery','input_suspend',
       'fg1_ibatt','fg2_ibatt','bq2597x_bus_voltage','bq2597x_bus_current','bq2597x_slave_bus_current']
for i in range(a.samples):
    assert read('getprop ro.serialno',False)=='603ac302'
    values={n:read('cat /sys/class/qcom-battery/'+n) for n in names}
    row=dict(time=time.time(),uptime=read('cat /proc/uptime'),nodes=values,
             usb_online=read('cat /sys/class/power_supply/usb/online'),
             battery_capacity=read('cat /sys/class/power_supply/battery/capacity'),
             battery_current=read('cat /sys/class/power_supply/battery/current_now'))
    report['samples'].append(row)
    (folder/'capture.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(sample=i,online=row['usb_online'],
          **{n:values[n] for n in ['pd_verifed','verify_process','adapter_id','apdo_max','power_max','quick_charge_type']})),flush=True)
    if i+1<a.samples:time.sleep(a.interval)
(folder/'auto-log.txt').write_text(read("dmesg | grep -e 'sheng PPS auto'")+'\n')
report['complete']=True;(folder/'capture.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(folder=str(folder),complete=True)),flush=True)

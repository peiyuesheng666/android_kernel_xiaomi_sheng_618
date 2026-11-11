#!/usr/bin/env python3
"""Read charging diagnostics over a serial-verified wireless ADB connection."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time

workspace = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--samples', type=int, default=1)
parser.add_argument('--interval', type=float, default=10)
parser.add_argument('--label', default='snapshot')
args = parser.parse_args()
assert 1 <= args.samples <= 60 and 0 <= args.interval <= 30
assert re.fullmatch(r'[a-z0-9-]+', args.label)
adb = [str(workspace/'tools/platform-tools/adb.exe'), '-s', '192.168.1.14:5555']

def read(command, root=False):
    if root:
        command = "su -c '" + command.replace("'", "'\"'\"'") + "'"
    result = subprocess.run(adb+['shell', command], capture_output=True, timeout=25)
    return dict(returncode=result.returncode,
                stdout=result.stdout.decode(errors='replace').strip(),
                stderr=result.stderr.decode(errors='replace').strip())

assert read('getprop ro.serialno')['stdout'] == '603ac302'
stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
output = workspace/'logs'/f'charging-{args.label}-{stamp}'
output.mkdir(parents=True, exist_ok=False)
nodes = '''real_type usb_real_type typec_mode pd_verifed apdo_max quick_charge_type
adapter_id adapter_svid power_max constant_power fastchg_mode authentic slave_authentic
verify_slave_flag input_suspend restrict_chg restrict_cur connector_temp average_temp
average_current fg1_fastcharge fg1_current_max bq2597x_chip_ok bq2597x_slave_chip_ok
bq2597x_battery_present bq2597x_slave_battery_present bq2597x_battery_voltage
bq2597x_bus_voltage bq2597x_bus_current bq2597x_slave_bus_current night_charging
smart_batt is_eu_model screen_cctog current_state'''.split()
state = dict(serial='603ac302', transport=adb[-1], label=args.label,
             read_only=True, samples=[], identity=read('uname -a; cat /proc/sys/kernel/random/boot_id'),
             batterysecret=read('getprop init.svc.batterysecret'),
             qcom_nodes=read('ls /sys/class/qcom-battery'))
for i in range(args.samples):
    assert read('getprop ro.serialno')['stdout'] == '603ac302'
    row = dict(time_utc=datetime.now(timezone.utc).isoformat(),
               uptime=read('cat /proc/uptime'),
               battery=read('cat /sys/class/power_supply/battery/uevent'),
               usb=read('cat /sys/class/power_supply/usb/uevent'),
               nodes={n:read('cat /sys/class/qcom-battery/'+n, root=True) for n in nodes})
    state['samples'].append(row)
    (output/'snapshot.json').write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(sample=i, usb=row['usb']['stdout'],
                         nodes={n:row['nodes'][n]['stdout'] for n in
                                ('real_type','pd_verifed','apdo_max','fastchg_mode','authentic','slave_authentic')})), flush=True)
    if i+1 < args.samples:
        time.sleep(args.interval)
dmesg = read('dmesg', root=True)
(output/'dmesg.log').write_text(dmesg['stdout']+'\n', encoding='utf-8')
(output/'charging-dmesg.log').write_text('\n'.join(line for line in dmesg['stdout'].splitlines()
    if re.search(r'BATTERY_CHG|batterysecret|batt.*auth|pd_verif|charger|fastchg', line, re.I))+'\n', encoding='utf-8')
print(json.dumps(dict(output=str(output), samples=len(state['samples']))), flush=True)

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture read-only USB evidence through an already connected ADB transport."""
from pathlib import Path
import argparse
import subprocess, datetime, hashlib, json
from zoneinfo import ZoneInfo
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--serial', required=True)
options=parser.parse_args()
project=Path(__file__).resolve().parents[1]
base=project/'reports/device'/('kernel618-usb-wireless-'+datetime.datetime.now(ZoneInfo('Asia/Singapore')).strftime('%Y%m%d-%H%M%S-%f'))
base.mkdir(parents=True)
adb=project/'tools/platform-tools/adb.exe'
serial=options.serial
commands={
'identity': 'id; uname -a; cat /proc/uptime; getprop sys.boot_completed; getenforce',
'properties': 'getprop',
'usb-manager': 'dumpsys usb',
'usb-sysfs': r'''for d in /sys/class/udc/* /sys/class/usb_role/* /sys/class/typec/* /sys/bus/platform/devices/*dwc* /sys/bus/platform/devices/*usb* /sys/bus/platform/devices/*hsphy* /sys/bus/platform/devices/*ssphy*; do [ -e "$d" ] || continue; echo DEVICE:$d; readlink -f "$d/driver"; for n in state current_speed maximum_speed function role data_role power_role port_type uevent power/runtime_status power/control power/runtime_active_time power/runtime_suspended_time; do [ -e "$d/$n" ] && { echo FILE:$n; cat "$d/$n"; }; done; done''',
'power-supply': r'''for d in /sys/class/power_supply/*; do echo DEVICE:$d; cat "$d/uevent"; done''',
'gadget': r'''ls -l /config/usb_gadget/g1; cat /config/usb_gadget/g1/UDC; ls -l /config/usb_gadget/g1/configs/b.1; ls -l /config/usb_gadget/g1/functions; ls -l /dev/usb-ffs/adb; ls -l /sys/class/android_usb/android0; cat /sys/class/android_usb/android0/state''',
'clocks': 'cat /sys/kernel/debug/clk/clk_summary; cat /sys/kernel/debug/clk/clk_orphan_summary; cat /sys/kernel/debug/devices_deferred',
'dmesg': 'dmesg',
'logcat-kernel': 'logcat -b kernel -d -v monotonic',
'logcat-all': 'logcat -b all -d -v threadtime',
}
receipt={}
for name,cmd in commands.items():
 try:
  p=subprocess.run([str(adb),'-s',serial,'shell',cmd],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45)
  data=p.stdout; (base/(name+'.txt')).write_bytes(data)
  receipt[name]={'returncode':p.returncode,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 except subprocess.TimeoutExpired:
  receipt[name]={'timeout':True}
(base/'receipt.json').write_text(json.dumps(receipt,indent=2))
(project/'reports/device/kernel618-current-usb-folder.txt').write_text(str(base.relative_to(project)))
print(base)
print(json.dumps(receipt,indent=2))

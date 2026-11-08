#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record stock keyboard HAL communication and input registration, without input injection."""
import argparse
import hashlib
import json
import re
import subprocess
import time
from test_sheng618_hardware import ROOT, SERIAL

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
options = parser.parse_args()
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.revision)
folder = ROOT/'reports/device'/('kernel618-'+options.revision)/('keyboard-'+str(time.time_ns()))
folder.mkdir(parents=True)
adb = [str(ROOT/'tools/platform-tools/adb.exe'), '-s', SERIAL, 'shell']
evidence = {}


def call(name, command):
    result = subprocess.run(adb+[command], capture_output=True, timeout=25)
    raw = result.stdout+result.stderr
    (folder/(name+'.txt')).write_bytes(raw)
    evidence[name] = dict(returncode=result.returncode, sha256=hashlib.sha256(raw).hexdigest())
    return raw.decode(errors='replace')


assert call('kernel', 'uname -r').strip().startswith('6.18.')
binding = call('binding', 'readlink /sys/bus/i2c/devices/5-004c/driver').strip()
node = call('node', 'ls -lZ /dev/nanodev0')
service = call('service', 'getprop init.svc.nanoapp').strip()
input_text = call('input', 'dumpsys input')
manager = input_text.split('MiuiKeyboardManager:', 1)[-1].split('INPUT MANAGER', 1)[0]
versions = {}
for name in ['keyboardVersion', 'MCUVersion', 'TouchPadVersion']:
    match = re.search(r'^\s+'+name+r':(\S+)', manager, re.M)
    versions[name] = match[1] if match else None
report = dict(revision=options.revision, evidence=str(folder.relative_to(ROOT)), files=evidence,
    driver_bound=binding.endswith('/nanosic_driver'), stock_node_labeled='u:object_r:nano_device:s0' in node,
    stock_service_running=service == 'running', versions=versions,
    keyboard_connected=bool(re.search(r'^\s+connect:true\s*$', manager, re.M)),
    keyboard_enabled=bool(re.search(r'^\s+enable:true\s*$', manager, re.M)),
    keyboard_input_registered=bool(re.search(r'^\s+\d+: Xiaomi Keyboard\s*$', input_text, re.M)),
    touchpad_input_registered=bool(re.search(r'^\s+\d+: Xiaomi Touchpad\s*$', input_text, re.M)),
    identity_state_reported=bool(re.search(r'^\s+mIdentityPass:true\s*$', manager, re.M)),
    input_injected=False, physical_keypress_and_touchpad_verified=False,
    limitations='Metadata and real stock HAL replies only; no physical keypress, pointer movement, hotplug or battery/charging acceptance')
(ROOT/'reports'/('kernel618-'+options.revision+'-keyboard.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

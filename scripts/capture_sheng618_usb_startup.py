#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture bounded startup evidence over existing root ADB, validating revision first."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
parser.add_argument('--serial', default='192.168.1.153:5555')
parser.add_argument('--connect-timeout', type=int, default=180)
parser.add_argument('--observe-seconds', type=int, default=120)
parser.add_argument('--mount-debugfs', action='store_true', help='Mount debugfs if absent for IPC evidence')
args = parser.parse_args()
assert re.fullmatch(r'hardware-r[0-9]+', args.revision)
assert 10 <= args.connect_timeout <= 600 and 0 <= args.observe_seconds <= 600
project = Path(__file__).resolve().parents[1]
adb = project / 'tools/platform-tools/adb.exe'
folder = project / ('reports/device/kernel618-' + args.revision) / (
    'usb-startup-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
folder.mkdir(parents=True, exist_ok=False)


def shell(command, timeout=20):
    return subprocess.run([str(adb), '-s', args.serial, 'shell', command],
                          capture_output=True, timeout=timeout)


identity_command = 'id; uname -r; cat /proc/cmdline; cat /proc/uptime; getenforce; getprop sys.boot_completed'
deadline = time.monotonic() + args.connect_timeout
next_notice = 0
while time.monotonic() < deadline:
    try:
        subprocess.run([str(adb), 'connect', args.serial], capture_output=True, timeout=5)
        identity = shell(identity_command, timeout=5)
        data = identity.stdout.decode(errors='replace')
        if 'uid=0(root)' in data and 'sheng_test=' + args.revision in data.split():
            (folder / 'identity.txt').write_bytes(identity.stdout + identity.stderr)
            break
    except subprocess.TimeoutExpired:
        pass
    if time.monotonic() >= next_notice:
        print('Waiting for authenticated root ADB and ' + args.revision, flush=True)
        next_notice = time.monotonic() + 30
    time.sleep(3)
else:
    raise TimeoutError('No verified root transport for this revision; no device settings changed')

commands = {
    'usb': 'cat /proc/uptime; cat /sys/class/power_supply/usb/uevent; cat /sys/class/power_supply/battery/status; cat /sys/class/android_usb/android0/state; cat /sys/class/typec/port0/data_role; cat /sys/class/typec/port0/power_role; getprop vendor.audio.usb_cctoggle; getprop dev.bootcomplete; for n in screen_cctog cc_toggle otg_ui_support input_suspend; do ls -lZ /sys/class/qcom-battery/$n; cat /sys/class/qcom-battery/$n; done',
    'ucsi': 'cat /sys/kernel/debug/ipc_logging/ucsi/log',
    'dwc3': 'cat /sys/kernel/debug/ipc_logging/a600000.ssusb/log',
    'kernel': 'dmesg',
    'logcat': 'logcat -b all -d -v threadtime',
}
receipt = dict(revision=args.revision, serial=args.serial,
               actual_root_and_revision_verified=True, device_settings_written=False,
               automatic_reboot_enabled=False, samples=[])
if args.mount_debugfs:
    result = shell('if grep -q "debugfs /sys/kernel/debug debugfs" /proc/mounts; then echo existing; else mount -t debugfs debugfs /sys/kernel/debug && echo mounted; fi')
    (folder / 'debugfs-mount.txt').write_bytes(result.stdout + result.stderr)
    receipt['debugfs_mount_created'] = result.returncode == 0 and b'mounted' in result.stdout
    receipt['device_settings_written'] = receipt['debugfs_mount_created']
start = time.monotonic()
number = 0
while True:
    sample = dict(elapsed_seconds=round(time.monotonic() - start, 2), files={})
    state = subprocess.run([str(adb), '-s', args.serial, 'get-state'], capture_output=True, timeout=5)
    if state.returncode or state.stdout.strip() != b'device':
        subprocess.run([str(adb), 'disconnect', args.serial], capture_output=True, timeout=5)
        try:
            subprocess.run([str(adb), 'connect', args.serial], capture_output=True, timeout=5)
        except subprocess.TimeoutExpired:
            pass
    for name, command in commands.items():
        if name == 'logcat' and number not in (0, 4):
            continue
        result = shell(command, timeout=35)
        blob = result.stdout + result.stderr
        filename = f'{number:02d}-{name}.txt'
        (folder / filename).write_bytes(blob)
        sample['files'][filename] = dict(returncode=result.returncode, bytes=len(blob),
                                          sha256=hashlib.sha256(blob).hexdigest())
        if name == 'usb':
            text = blob.decode(errors='replace')
            valid = result.returncode == 0 and 'POWER_SUPPLY_ONLINE=' in text
            sample['usb_status_readable'] = valid
            sample['usb_online'] = ('POWER_SUPPLY_ONLINE=1' in text) if valid else None
            sample['usb_configured'] = ('CONFIGURED' in text) if valid else None
    receipt['samples'].append(sample)
    (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in sample.items() if k != 'files'}), flush=True)
    if time.monotonic() - start >= args.observe_seconds:
        break
    time.sleep(min(30, args.observe_seconds - (time.monotonic() - start)))
    number += 1
print(str(folder), flush=True)

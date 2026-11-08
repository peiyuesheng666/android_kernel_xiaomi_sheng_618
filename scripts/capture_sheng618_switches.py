#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read native fingerprint/hall binding evidence; never simulate authentication."""
import argparse
import hashlib
import json
import subprocess
import time
from test_sheng618_hardware import ROOT, SERIAL

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
options = parser.parse_args()
folder = ROOT/'reports/device'/('kernel618-'+options.revision)/('switches-'+str(time.time_ns()))
folder.mkdir(parents=True)
commands = {
    'bindings': 'uname -r; for p in /sys/bus/platform/devices/soc:fingerprint_fpc /sys/bus/platform/devices/soc:xiaomi_fingerprint /sys/bus/platform/devices/soc:xiaomi_hall; do ls -ld "$p/driver"; done',
    'fingerprint': 'dumpsys fingerprint; ps -A | grep -i fingerprint; getprop | grep -i fpc',
    'hall': 'dumpsys input; cat /proc/interrupts',
    'nfc': 'dumpsys nfc; pm list features | grep -i nfc; service list | grep -i nfc; ls -l /dev/pn* /dev/nq* /dev/st21*',
}
results = {}
for name, cmd in commands.items():
    result = subprocess.run([str(ROOT/'tools/platform-tools/adb.exe'), '-s', SERIAL, 'shell', cmd],
                            capture_output=True, timeout=30)
    data = result.stdout + result.stderr
    (folder/(name+'.txt')).write_bytes(data)
    results[name] = dict(command=cmd, returncode=result.returncode, bytes=len(data),
                         sha256=hashlib.sha256(data).hexdigest())
report = dict(revision=options.revision, evidence=str(folder.relative_to(ROOT)), captures=results,
    acceptance='Binding and framework initialization only; real cover transitions and biometric enrollment/authentication require physical verification')
(ROOT/'reports'/('kernel618-'+options.revision+'-switches.json')).write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Step framework brightness, read both KTZ chips, then restore user settings."""
import argparse
import json
import subprocess
import time
from test_sheng618_hardware import ROOT, SERIAL

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
options = parser.parse_args()
folder = ROOT/'reports/device'/('kernel618-'+options.revision)/('brightness-'+str(time.time_ns()))
folder.mkdir(parents=True)
receipt = dict(revision=options.revision, samples=[], restored=False)

def call(cmd):
    r = subprocess.run([str(ROOT/'tools/platform-tools/adb.exe'), '-s', SERIAL, 'shell', cmd],
                       capture_output=True, text=True, timeout=15)
    output = r.stdout + r.stderr
    with (folder/'control.txt').open('a') as log:
        log.write(f'{cmd}: rc={r.returncode}\n{output}\n')
    assert r.returncode == 0, output
    return output.strip()

assert call('uname -r').startswith('6.18.')
original = float(call('cmd display get-brightness 0'))
assert 0 <= original <= 1
mode = call('settings get system screen_brightness_mode')
saved_int = call('settings get system screen_brightness')
saved_float = call('settings get system screen_brightness_float')
receipt['original_brightness'] = original
receipt['original_mode'] = mode
try:
    call('settings put system screen_brightness_mode 0')
    call('input keyevent 224')
    for level in (0.15, 0.60, 0.15):
        call('cmd display set-brightness '+str(level))
        time.sleep(1.5)
        sample = dict(requested=level, framework=call('cmd display get-brightness 0'))
        for chip in ('0-0011', '4-0011'):
            try:
                sample[chip] = call('cat /sys/bus/i2c/devices/'+chip+'/register_brightness')
            except AssertionError as error:
                sample[chip] = str(error).strip()
        receipt['samples'].append(sample)
finally:
    call('cmd display set-brightness '+str(original))
    call('settings put system screen_brightness '+saved_int)
    if saved_float == 'null':
        call('settings delete system screen_brightness_float')
    else:
        call('settings put system screen_brightness_float '+saved_float)
    call('settings put system screen_brightness_mode '+mode)
    receipt['restored'] = call('settings get system screen_brightness_mode') == mode
    receipt['evidence'] = str(folder.relative_to(ROOT))
    (ROOT/'reports'/('kernel618-'+options.revision+'-brightness.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

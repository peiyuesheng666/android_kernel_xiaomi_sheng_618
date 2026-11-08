#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Flash one non-test candidate and verify its actual ADB kernel and Android completion."""
import argparse
import json
import re
import subprocess
import time
from test_sheng618_hardware import ROOT, SERIAL, sha, win

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
options = parser.parse_args()
tag = options.revision
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', tag)
delivery = ROOT / ('artifacts/sheng-6.18-' + tag)
build = json.loads((delivery / 'build-result.json').read_text())
assert build['revision'] == tag and build['test_timeout_seconds'] is None
assert sha(delivery / 'boot.img') == build['boot_sha256']
assert sha(delivery / 'Image') == build['image_sha256']
folder = ROOT / ('reports/device/kernel618-' + tag)
folder.mkdir(parents=True, exist_ok=True)
assert not (folder / 'flash.txt').exists(), 'Preserve previous flash records'
report = ROOT / ('reports/kernel618-' + tag + '-hardware.json')
receipt = dict(revision=tag, boot_sha256=build['boot_sha256'], image_sha256=build['image_sha256'],
               writes=['boot_a'], test_mode_enabled=False, events=[], full_hardware_functionality_verified=False,
               wired_adb_timeout_seconds=300, stop_task_if_wired_adb_absent=True,
               adb_transport='USB', adb_serial=SERIAL)

def record(event, **data):
    receipt['events'].append(dict(event=event, time=time.strftime('%Y-%m-%dT%H:%M:%S%z'), **data))
    report.write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt['events'][-1]), flush=True)

def call(tool, *args, timeout=20, check=True):
    result = subprocess.run([str(ROOT / ('tools/platform-tools/' + tool + '.exe')), '-s', SERIAL, *args],
                            capture_output=True, timeout=timeout)
    text = (result.stdout + result.stderr).decode(errors='replace')
    with (folder / 'control.txt').open('a') as stream:
        stream.write(f'{tool} {args!r}: rc={result.returncode}\n{text}\n')
    if check and result.returncode:
        raise RuntimeError(text)
    return text

try:
    deadline = time.monotonic() + 60
    while not re.search(SERIAL + r'\s+fastboot', call('fastboot', 'devices')):
        if time.monotonic() >= deadline:
            raise TimeoutError('Fastboot missing after 60 seconds; no partition written')
        time.sleep(1)
    for name, expected in [('product', 'sheng'), ('current-slot', 'a'), ('unlocked', 'yes'), ('is-userspace', 'no')]:
        assert re.search(name + r':\s*' + expected + r'\b', call('fastboot', 'getvar', name))
    flash = call('fastboot', 'flash', 'boot_a', win(delivery / 'boot.img'), timeout=180)
    assert 'OKAY' in flash and 'FAILED' not in flash
    (folder / 'flash.txt').write_text(flash)
    record('boot_a_flashed')
    call('fastboot', 'reboot')
    start = time.monotonic()
    next_notice = 0
    captured = False
    while time.monotonic() - start < receipt['wired_adb_timeout_seconds']:
        devices = call('adb', 'devices', check=False)
        if re.search(SERIAL + r'\s+device\b', devices):
            kernel = call('adb', 'shell', 'uname -r').strip()
            assert kernel.startswith('6.18.')
            if build.get('build_identity'):
                assert kernel == build['build_identity']['release'], kernel
            cmdline = call('adb', 'shell', 'cat /proc/cmdline', check=False).strip()
            receipt['live_cmdline_readable'] = 'Permission denied' not in cmdline and bool(cmdline)
            if receipt['live_cmdline_readable']:
                assert 'sheng_test=' + tag in cmdline.split(), cmdline
            if not receipt.get('candidate_adb_connected'):
                receipt['candidate_adb_connected'] = True
                receipt['kernel'] = kernel
                record('candidate_adb_connected', elapsed_seconds=round(time.monotonic()-start, 2))
            if call('adb', 'shell', 'getprop sys.boot_completed').strip() == '1':
                receipt['android_boot_completed'] = True
                if not captured:
                    for name, command in [('properties', 'getprop'), ('input', 'dumpsys input'),
                                          ('sensors', 'dumpsys sensorservice'), ('logcat', 'logcat -b all -d -t 5000'),
                                          ('audio-policy', 'dumpsys media.audio_policy'),
                                          ('usb', 'dumpsys usb')]:
                        (folder / (name+'.txt')).write_text(call('adb', 'shell', command, check=False, timeout=30))
                    captured = True
                    record('android_boot_completed', elapsed_seconds=round(time.monotonic()-start, 2))
        if time.monotonic() >= next_notice:
            next_notice = time.monotonic()+30
            record('waiting_for_android', elapsed_seconds=round(time.monotonic()-start, 2))
        time.sleep(2)
    devices = call('adb', 'devices', check=False)
    available = bool(re.search(SERIAL + r'\s+device\b', devices))
    if available:
        # A listed transport alone does not prove that adbd can execute commands.
        available = call('adb', 'shell', 'uname -r', check=False).strip() == build['build_identity']['release']
    receipt['stop_required'] = not available
    record('wired_adb_deadline_reached', elapsed_seconds=round(time.monotonic()-start, 2),
           wired_adb_observed=receipt.get('candidate_adb_connected', False),
           wired_adb_available_at_deadline=available, stop_required=receipt['stop_required'])
    if not available:
        raise TimeoutError('USB ADB absent at the 300-second deadline; preserve results and stop task')
except Exception as error:
    record('failed', error=str(error))
    raise

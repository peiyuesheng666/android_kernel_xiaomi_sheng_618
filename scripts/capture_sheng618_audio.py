#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only, bounded playback diagnostics over the candidate's ADB connection."""
import argparse
import json
import re
import subprocess
import time
from test_sheng618_hardware import ROOT, SERIAL

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
parser.add_argument('--seconds', type=int, default=45)
options = parser.parse_args()
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.revision)
assert 10 <= options.seconds <= 120
folder = ROOT / 'reports/device' / ('kernel618-' + options.revision) / ('audio-' + str(time.time_ns()))
folder.mkdir(parents=True)
adb = [str(ROOT / 'tools/platform-tools/adb.exe'), '-s', SERIAL]

def capture(name, command):
    result = subprocess.run(adb + ['shell', command], capture_output=True, timeout=20)
    (folder / (name + '.txt')).write_bytes(result.stdout + result.stderr)
    return result.stdout.decode(errors='replace').strip()

assert capture('kernel', 'uname -r').startswith('6.18.')
capture('start', 'date; cat /proc/uptime')
start = time.monotonic()
index = 0
while True:
    capture(f'flinger-{index}', 'dumpsys media.audio_flinger')
    capture(f'top-{index}', 'top -H -b -n 1 -m 35')
    print(json.dumps(dict(sample=index, elapsed=round(time.monotonic()-start, 1))), flush=True)
    if time.monotonic() - start >= options.seconds:
        break
    index += 1
    time.sleep(min(10, max(0, options.seconds - (time.monotonic() - start))))
capture('policy', 'dumpsys media.audio_policy')
capture('logcat', 'logcat -b all -d -s AudioFlinger AudioTrack AudioStreamOut '
        'audio_hw_primary audio_hw_utils audio_hw_extn PerfSense AGM AgmService '
        'ResourceManager StreamPCM StreamCompress SessionAlsaPcm SessionAlsaCompress')
capture('end', 'date; cat /proc/uptime')
print(str(folder), flush=True)

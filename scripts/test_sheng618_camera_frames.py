#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded real-camera frame test. Pixel buffers are only discarded in RAM."""
import argparse
import hashlib
import json
import subprocess
import time
from build_sheng618_upstream import ROOT as BUILD
from test_sheng618_hardware import ROOT, SERIAL, win

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
options = parser.parse_args()
folder = ROOT/'reports/device'/('kernel618-'+options.revision)/('camera-frames-'+str(time.time_ns()))
folder.mkdir(parents=True)
binary = BUILD/'diagnostic/camera-test/sheng-camera-frames'
adb = [str(ROOT/'tools/platform-tools/adb.exe'), '-s', SERIAL]
assert subprocess.check_output(adb+['shell','uname -r']).decode().startswith('6.18.')
subprocess.run(adb+['push',win(binary),'/data/local/tmp/sheng-camera-frames'],check=True,capture_output=True)
subprocess.run(adb+['shell','chmod 755 /data/local/tmp/sheng-camera-frames'],check=True)
try:
    result = subprocess.run(adb+['shell','/data/local/tmp/sheng-camera-frames'],capture_output=True,timeout=55)
    text = (result.stdout+result.stderr).decode(errors='replace')
    code = result.returncode
except subprocess.TimeoutExpired as error:
    text = ((error.stdout or b'')+(error.stderr or b'')).decode(errors='replace')
    code = 'timeout'
(folder/'frames.txt').write_text(text)
for name, command in {
    'logcat':'logcat -b all -d -t 14000 | grep -iE "camx|camera3|ndkcamera|imageReader|camera.*(error|fail)|cam_sensor|cam_req|csiphy|gralloc|mapper|Allocator|BufferQueue|GraphicBuffer"',
    'service':'dumpsys media.camera',
}.items():
    data = subprocess.run(adb+['shell',command],capture_output=True,timeout=25)
    (folder/(name+'.txt')).write_bytes(data.stdout+data.stderr)
subprocess.run(adb+['shell','rm -f /data/local/tmp/sheng-camera-frames'],check=True)
report = dict(revision=options.revision,evidence=str(folder.relative_to(ROOT)),returncode=code,
              result=text,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),pixels_saved=False)
(ROOT/'reports'/('kernel618-'+options.revision+'-camera-frames.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

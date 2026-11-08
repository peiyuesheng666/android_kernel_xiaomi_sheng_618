#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise stock camera preview without taking or saving a photograph."""
import argparse
import json
import re
import subprocess
import time
from test_sheng618_hardware import ROOT, SERIAL

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
parser.add_argument('--front', action='store_true')
options = parser.parse_args()
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.revision)
folder = ROOT/'reports/device'/('kernel618-'+options.revision)/('preview-'+str(time.time_ns()))
folder.mkdir(parents=True)
adb = [str(ROOT/'tools/platform-tools/adb.exe'), '-s', SERIAL, 'shell']


def call(name, command):
    result = subprocess.run(adb+[command], capture_output=True, timeout=25)
    data = result.stdout + result.stderr
    (folder/(name+'.txt')).write_bytes(data)
    return data.decode(errors='replace')


assert call('kernel', 'uname -r').strip().startswith('6.18.')
try:
    call('wake', 'input keyevent 224')
    policy = call('keyguard-policy', 'dumpsys window policy')
    if re.search(r'^\s+secure=false\s*$', policy, re.M):
        # Normal OS dismissal of an unsecured swipe screen. Never attempt to
        # dismiss a credential-protected keyguard or guess user credentials.
        call('dismiss-unsecured-swipe', 'wm dismiss-keyguard')
        action = 'android.media.action.STILL_IMAGE_CAMERA'
    else:
        action = 'android.media.action.STILL_IMAGE_CAMERA_SECURE'
    extra = ''
    if options.front:
        call('close-previous-test', 'am force-stop com.android.camera')
        extra = ' --ez android.intent.extra.USE_FRONT_CAMERA true --ei android.intent.extras.CAMERA_FACING 1'
    call('start', 'am start -a '+action+extra)
    for i in range(4):
        time.sleep(5)
        call('camera-'+str(i), 'dumpsys media.camera')
        print(json.dumps(dict(sample=i)), flush=True)
    call('focus', 'dumpsys window | grep -E "mCurrentFocus|mFocusedApp"')
    call('logcat', 'logcat -b all -d -t 12000 | grep -iE "camx|camera3|cam_req|cam_sensor|camera.*(error|fail)|surface.*(error|fail)|gralloc|GraphicBuffer|BufferQueue"')
finally:
    call('close', 'input keyevent 3')
print(str(folder), flush=True)

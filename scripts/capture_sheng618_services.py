#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture bounded, read-only camera/display/audio diagnostics on native 6.18."""
import argparse
import json
import re
import subprocess
import time
from test_sheng618_hardware import ROOT, SERIAL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    options = parser.parse_args()
    assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.revision)
    folder = ROOT / 'reports/device' / ('kernel618-' + options.revision) / ('services-' + str(time.time_ns()))
    folder.mkdir(parents=True)
    adb = [str(ROOT / 'tools/platform-tools/adb.exe'), '-s', SERIAL]
    receipt = {}

    def capture(name, command):
        try:
            result = subprocess.run(adb + ['shell', command], capture_output=True, timeout=25)
            data, code = result.stdout + result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            data, code = (error.stdout or b'') + (error.stderr or b''), 'timeout'
        (folder / (name + '.txt')).write_bytes(data)
        receipt[name] = dict(command=command, returncode=code, bytes=len(data))
        (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(dict(name=name, **receipt[name])), flush=True)
        return data.decode(errors='replace').strip()

    assert capture('kernel', 'uname -r').startswith('6.18.')
    commands = {
        'camera': 'dumpsys media.camera',
        'camera-processes': 'ps -A | grep -iE "camera|provider"; getprop | grep -i camera; ls -l /dev/video* /dev/v4l-subdev* /dev/media* /dev/cam*',
        'camera-logcat': 'logcat -b all -d -t 12000 | grep -iE "camx|chiusecase|chi_feature|cameraprovider|camera.provider|camera-server|cameraserver|cam_req|cam-sensor|cam_sensor|cam_isp|cam_csiphy|camera.*(error|fail)|provider.*(error|fail)"',
        'crashes': 'logcat -b crash -d -t 400',
        'display': 'dumpsys display',
        'lights': 'dumpsys android.hardware.light.ILights/default; dumpsys lights; settings get system screen_brightness; settings get system screen_brightness_float; settings get system screen_brightness_mode',
        'backlight': 'for p in /sys/class/backlight/*; do echo "$p"; ls -l "$p"; for f in brightness actual_brightness max_brightness bl_power type; do echo "$f"; cat "$p/$f"; done; done; ls -l /sys/class/drm',
        'display-logcat': 'logcat -b all -d -t 10000 | grep -iE "backlight|setbrightness|set_brightness|setlight|displaybrightness|brightness.*(fail|error)|sde.*(fail|error)|dsi.*(fail|error)"',
        'audio-logcat': 'logcat -b all -d -t 16000 | grep -iE "underrun|overrun|xrun|pcm.*(fail|error)|cs35l43|snd_soc|AudioOut|audio.*(fail|error)|charger|power_supply|usb.*(connect|disconnect)"',
        'audio-flinger': 'dumpsys media.audio_flinger',
        'interrupts': 'cat /proc/uptime; cat /proc/interrupts',
        'fingerprint': 'dumpsys fingerprint; ls -l /sys/bus/platform/devices/soc:fingerprint_fpc /sys/bus/platform/devices/soc:xiaomi_fingerprint; logcat -b all -d -t 6000 | grep -iE "fpc|fingerprint.*(error|fail)|biometrics.*(error|fail)"',
        'nfc': 'dumpsys nfc; pm list features | grep -i nfc; getprop | grep -i nfc; ls -l /dev/pn* /dev/nq* /dev/st21*; logcat -b all -d -t 6000 | grep -iE "nqnfc|nfc.*(error|fail)"',
    }
    for name, command in commands.items():
        capture(name, command)
    print(str(folder), flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect bounded, read-only performance evidence from an explicit ADB device."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time
from zoneinfo import ZoneInfo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    options = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    stamp = datetime.datetime.now(ZoneInfo('Asia/Singapore')).strftime('%Y%m%d-%H%M%S-%f')
    folder = project/'reports/device'/('kernel618-performance-'+stamp)
    folder.mkdir(parents=True)
    adb = [str(project/'tools/platform-tools/adb.exe'), '-s', options.serial, 'shell']
    receipt = dict(serial=options.serial, evidence=str(folder.relative_to(project)), files={},
                   device_settings_changed=False, physical_smoothness_verified=False)

    def capture(name, command, timeout=25):
        try:
            result = subprocess.run(adb+[command], capture_output=True, timeout=timeout)
            raw = result.stdout+result.stderr
            (folder/(name+'.txt')).write_bytes(raw)
            receipt['files'][name] = dict(returncode=result.returncode, bytes=len(raw),
                                         sha256=hashlib.sha256(raw).hexdigest())
        except subprocess.TimeoutExpired:
            receipt['files'][name] = dict(timeout=True)
        (folder/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(json.dumps(dict(captured=name, **receipt['files'][name])), flush=True)

    capture('identity', 'date; uname -a; cat /proc/uptime; getprop sys.boot_completed')
    for index in range(2):
        capture(f'cpu-{index}', r'''cat /proc/loadavg; cat /proc/stat; cat /proc/pressure/cpu; cat /proc/pressure/io; cat /proc/pressure/memory; cat /sys/devices/system/cpu/online; for d in /sys/devices/system/cpu/cpufreq/policy*; do echo DEVICE:$d; for n in scaling_governor scaling_cur_freq scaling_min_freq scaling_max_freq cpuinfo_max_freq affected_cpus stats/time_in_state; do echo FILE:$n; cat "$d/$n"; done; done''')
        capture(f'gpu-{index}', r'''for d in /sys/class/kgsl/kgsl-3d0; do for n in gpuclk gpubusy num_pwrlevels default_pwrlevel min_pwrlevel max_pwrlevel thermal_pwrlevel devfreq/governor devfreq/cur_freq devfreq/min_freq devfreq/max_freq; do echo FILE:$n; cat "$d/$n"; done; done''')
        capture(f'top-{index}', 'top -H -b -n 1 -m 40')
        if index == 0:
            time.sleep(5)
    for name, command in (
        ('thermal', 'dumpsys thermalservice'),
        ('power', 'dumpsys power'),
        ('display', 'dumpsys display'),
        ('surfaceflinger', 'dumpsys SurfaceFlinger'),
        ('launcher-frames', 'dumpsys gfxinfo com.miui.home framestats'),
        ('systemui-frames', 'dumpsys gfxinfo com.android.systemui framestats'),
        ('audio', 'dumpsys media.audio_flinger'),
        ('memory', 'cat /proc/meminfo; cat /proc/vmstat; dumpsys cpuinfo'),
        ('logcat', 'logcat -b all -d -t 6000'),
    ):
        capture(name, command, timeout=40)
    print(folder, flush=True)


if __name__ == '__main__':
    main()

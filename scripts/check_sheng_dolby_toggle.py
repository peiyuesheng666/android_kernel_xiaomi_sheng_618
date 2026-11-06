#!/usr/bin/env python3
"""Operate the observed Dolby switch and record its retained native handle."""
from pathlib import Path
import argparse
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET

workspace = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('state', choices=('on', 'off', 'read'))
parser.add_argument('--label', required=True)
args = parser.parse_args()
adb = [str(workspace/'tools/platform-tools/adb.exe'), '-s', 'ca10ede3']
out = workspace/'reports/device/dolby-followup-20261106'
def shell(command):
    return subprocess.run([*adb, 'shell', command], check=True, capture_output=True,
                          text=True, encoding='utf-8', errors='replace', timeout=25).stdout
def state():
    shell('uiautomator dump /data/local/tmp/dolby-ui.xml')
    root = ET.fromstring(shell('cat /data/local/tmp/dolby-ui.xml'))
    nodes = [n for n in root.iter('node') if n.get('package') == 'org.lineageos.sheng.dolby']
    toggle = next(n for n in nodes if n.get('class') == 'android.widget.Switch')
    return toggle, [n.get('text') for n in nodes if n.get('text')]
shell('am start -n org.lineageos.sheng.dolby/.AtmosActivity')
toggle, texts = state()
requested = toggle.get('checked') == 'true'
if args.state != 'read' and requested != (args.state == 'on'):
    if 'org.lineageos.sheng.dolby' not in shell('dumpsys window | grep mCurrentFocus'):
        raise SystemExit('The user changed the foreground app; no tap sent.')
    x1, y1, x2, y2 = map(int, re.findall(r'\d+', toggle.get('bounds')))
    shell(f'input tap {(x1+x2)//2} {(y1+y2)//2}')
    time.sleep(2)
    toggle, texts = state()
flinger = shell('dumpsys media.audio_flinger')
log = shell('logcat -d -v threadtime -t 4000')
dms = shell('CLASSPATH=/data/local/tmp/sheng-dms-state-probe.jar app_process /system/bin ShengDmsStateProbe')
pids = shell('ps -A | grep -E "android.hardware.audio.service|audioserver|org.lineageos.sheng.dolby"')
(out/f'{args.label}-flinger.txt').write_text(flinger)
(out/f'{args.label}-log.txt').write_text(log)
(out/f'{args.label}-dms.txt').write_text(dms)
result = {'switch_checked': toggle.get('checked'), 'ui': texts, 'processes': pids,
          'dap_effect_registered': '- name: DAP_offload' in flinger,
          'native_enable_events': [line for line in log.splitlines()
              if 'doSetDapModuleEnabled() DAP module enabled' in line][-8:]}
(out/f'{args.label}-state.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))

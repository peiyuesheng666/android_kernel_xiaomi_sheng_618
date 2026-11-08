#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit the recovered device's actual panel timing/FPS mapping, without edits."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess

work = Path(__file__).resolve().parents[1]
dtb = work / 'reports/device/kernel618-usb-reference/live.dtb'
panel = '/soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_n81a_36_02_0a_duledsi_dsc_vid'


def get(node, prop, kind='u'):
    return subprocess.check_output(['fdtget', '-t', kind, str(dtb), node, prop], text=True).strip()


assert 'mi,video-mode-multi-timing' in subprocess.check_output(
    ['fdtget', '-p', str(dtb), panel], text=True).splitlines()
global_fps = list(map(int, get(panel, 'qcom,dsi-supported-dfps-list').split()))
root = panel + '/qcom,mdss-dsi-display-timings'
children = subprocess.check_output(['fdtget', '-l', str(dtb), root], text=True).splitlines()
rows = []
for child in children:
    node = root + '/' + child
    rates = list(map(int, get(node, 'mi,mdss-dsi-supported-fps-list').split()))
    rows.append({'node': child, 'base_fps': int(get(node, 'qcom,mdss-dsi-panel-framerate')),
                 'supported_fps': rates,
                 'width_per_controller': int(get(node, 'qcom,mdss-dsi-panel-width')),
                 'height': int(get(node, 'qcom,mdss-dsi-panel-height')),
                 'topology': list(map(int, get(node, 'qcom,display-topology').split()))})
coverage = collections.Counter(rate for row in rows for rate in row['supported_fps'])
assert set(coverage) == set(global_fps) and all(n == 1 for n in coverage.values())
assert len(global_fps) == len(set(global_fps))
report = {'dtb_sha256': hashlib.sha256(dtb.read_bytes()).hexdigest(), 'panel_node': panel,
          'mi_multi_timing': True, 'global_fps': global_fps, 'timings': rows,
          'every_global_rate_maps_to_exactly_one_timing': True,
          'old_driver_declared_modes': len(children) * len(global_fps),
          'old_driver_initialized_modes': len(global_fps),
          'correct_modes': len(global_fps), 'correct_timings': len(children),
          'scope': 'Read-only actual hardware DT compatibility audit; not kernel execution'}
(work / 'reports/kernel618-display-multitiming-dt.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

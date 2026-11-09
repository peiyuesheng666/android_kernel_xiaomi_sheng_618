#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record the captured r37 recovery while preserving the user's unplugged interval."""
import hashlib
import json
import re
from pathlib import Path

project = Path(__file__).resolve().parents[1]
folder = project / 'reports/device/kernel618-hardware-r37'
kernel = (folder / 'kernel-usb-recovered.txt').read_text()
ucsi = (folder / 'ucsi-recovered.txt').read_text()
status = (folder / 'usb-recovered.txt').read_text()
match = re.search(r'\[\s*([0-9.]+)[^\]]*\] dwc3_msm_set_role: cur_role:NONE new_role:DEVICE',
                  (folder / 'dwc3-recovered.txt').read_text())
assert match
role_time = float(match[1])
assert 'POWER_SUPPLY_ONLINE=1' in status and 'CONFIGURED' in status
assert 'source [sink]' in status and 'host [device]' in status
assert 'USB_STATE=CONFIGURED' in kernel
assert '848.139' in ucsi and '04 0a 2b 20' in ucsi
names = ['kernel-usb-recovered.txt', 'ucsi-recovered.txt', 'dwc3-recovered.txt',
         'usb-recovered.txt', 'gpio-recovered.txt', 'logcat-usb-recovered.txt',
         'charger-firmware-init.txt', 'charger-firmware-verbose.txt',
         'charger-init-logging-control.txt', 'charger-logging-control.txt']
evidence = {name: dict(bytes=(folder / name).stat().st_size,
                      sha256=hashlib.sha256((folder / name).read_bytes()).hexdigest()) for name in names}
report = dict(revision='hardware-r37', date='2026-11-09',
              usb_recovered_on_replug=True, recovered_device_role_uptime_seconds=role_time,
              user_confirmed_same_cable_and_pc_port=True,
              user_confirmed_pc_disconnected_during_intermediate_interval=True,
              continuous_connected_failure_duration_measured=False,
              fixed_40_minute_recovery_threshold_proven=False,
              firmware_ucsi_notification_before_dwc3_role=True,
              recovery_status=dict(udc='CONFIGURED', usb_online=1, power_role='sink', data_role='device',
                                   voltage_uv=4744000, current_ua=1112000),
              firmware_init_observation='Stored initialization log initially reports bPlugIn=1, but subsequent GET_CONNECTOR_STATUS returns disconnected. Stored firmware timestamps and log retrieval timestamps are distinct.',
              usb_fixed=False,
              limitation='No fixed delay or continuous failure window can be inferred while cable was disconnected; same-port early failure and later recovery are user-confirmed.',
              evidence=evidence)
(project / 'reports/kernel618-usb-recovery-r37.json').write_text(json.dumps(report, indent=2) + '\n')
followup_path = project / 'reports/kernel618-hardware-r37-followup.json'
followup = json.loads(followup_path.read_text())
followup['user_confirmed'].update(usb_recovered_on_later_replug=True,
                                pc_disconnected_during_intermediate_interval=True,
                                same_cable_and_pc_port=True)
followup['usb_status'] = 'Later replug at uptime 848.14s: UDC CONFIGURED, USB ONLINE=1, sink/device, about 4.744V and 1.112A. Earlier failed replug remains confirmed.'
followup['usb_startup_delay_fixed'] = False
followup['continuous_failure_duration_measured'] = False
followup['usb_recovery_report'] = 'reports/kernel618-usb-recovery-r37.json'
followup_path.write_text(json.dumps(followup, indent=2) + '\n')
print(json.dumps(report, indent=2))

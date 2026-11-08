#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record only the USB serial and boot-chain facts from the pinned reference."""
import hashlib
import json
from pathlib import Path

work = Path(__file__).resolve().parents[1]
cache = work / 'tools/anyhmos-usb-reference'
revision = json.loads((cache / 'commit.json').read_text(encoding='utf-8-sig'))['sha']
assert revision == '8095782bddbb9e9a74a4b5aaf9b9aef82c743ebb'
names = ['compat/bootstrap/init_entry.c', 'compat/bootstrap/hmos_probe_v121.c',
         'compat/bootstrap/probe_serial_v121.inc', 'output/Flash-Current.ps1',
         'output/Capture-Serial.ps1', 'tools/build_promax_ramdisk.py', 'README.md']
files = {name: {'sha256': hashlib.sha256((cache / name).read_bytes()).hexdigest()}
         for name in names}
probe = (cache / names[1]).read_text()
usb = probe[probe.index('static void usb_setup(void)'):probe.index('static void usb_setup(void)') + 4500]
assert usb.index('put(mode,"peripheral")') < usb.index('opendir("/sys/class/udc")')
assert 'functions/acm.usb0' in usb and '0x1d6b' in usb and '0x0104' in usb
report = {'repository': 'https://github.com/AnyHarmonyOSNext/anyhmos_xiaomi_sheng',
          'revision': revision, 'files': files,
          'usb_boot_chain': {
              'init_boot': '/init minimal PID1 entry transfers to /sheng-compat-v118/hmos-probe',
              'vendor_boot': 'ramdisk holds hmos-probe; USB portion sets peripheral mode and creates ACM gadget',
              'boot': 'kernel/USB support; supplied Desktop boot has no ramdisk and no built-in initramfs',
              'latest_flash_script': 'writes vendor_boot_a only; requires previously installed matching init_boot entry'},
          'usb': {'vendor_id': '1d6b', 'product_id': '0104', 'function': 'acm.usb0',
                  'device_tty': '/dev/ttyGS0', 'windows_port': 'COM port',
                  'controller_mode_before_waiting_for_udc': True,
                  'history_replay': 'reference collector sends replay; our collector streams backlog directly'},
          'applied_reference_scope': 'USB peripheral-before-UDC ordering and standard ACM descriptors only',
          'hmos_bootstrap_or_services_imported': False,
          'supplied_boot_live_test': {'kernel': '5.15.178-android13-8-00021-g6f2f96be86b9-ab13729987',
                                     'android_boot_completed': True,
                                     'observed_usb': '18d1:4e11 ADB; no COM observed with stock init_boot/vendor_boot'},
          'six_eighteen_crash_location_known': False,
          'reference_is_not_six_eighteen_runtime_evidence': True}
(work / 'reports/kernel618-anyhmos-usb-reference.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

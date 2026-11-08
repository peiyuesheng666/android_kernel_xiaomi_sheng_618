#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Retain stock sheng 5.15 firmware SELinux ABI without changing other load checks."""
import difflib
import hashlib
import json
from build_sheng618_upstream import ACK, PROJECT

path = ACK / 'security/selinux/hooks.c'
receipt = PROJECT / 'reports/kernel618-firmware-lsm-source.json'
changes = []
for kind, file in [('READING', 'file'), ('LOADING', 'NULL')]:
    old = ('\tcase ' + kind + '_FIRMWARE:\n'
           '\t\trc = selinux_kernel_load_from_file(' + file + ', SYSTEM__FIRMWARE_LOAD);\n'
           '\t\tbreak;')
    new = ('\tcase ' + kind + '_FIRMWARE:\n'
           '\t\t/* Stock sheng 5.15 policy predates system:firmware_load.\n'
           '\t\t * Ordinary file/sysfs access and other LSMs still apply.\n'
           '\t\t */\n'
           '\t\tif (!IS_ENABLED(CONFIG_SHENG_LEGACY_FIRMWARE_LSM))\n'
           '\t\t\trc = selinux_kernel_load_from_file(' + file + ',\n'
           '\t\t\t\t\t\t   SYSTEM__FIRMWARE_LOAD);\n'
           '\t\tbreak;')
    changes.append((old, new))
before = path.read_text()
if all(new in before for _, new in changes):
    for old, new in changes:
        assert before.count(new) == 1
        before = before.replace(new, old, 1)
after = before
for old, new in changes:
    assert after.count(old) == 1, old
    after = after.replace(old, new, 1)
path.write_text(after)
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/firmware-lsm-compat.patch').write_text(
    ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='a/security/selinux/hooks.c', tofile='b/security/selinux/hooks.c', n=0)))
kconfig = ACK / 'security/selinux/Kconfig'
if 'config SHENG_LEGACY_FIRMWARE_LSM\n' not in kconfig.read_text():
    with kconfig.open('a') as stream:
        stream.write('\nconfig SHENG_LEGACY_FIRMWARE_LSM\n'
                     '\tbool "Sheng stock 5.15 firmware SELinux contract"\n'
                     '\tdepends on SECURITY_SELINUX && FW_LOADER\n'
                     '\thelp\n'
                     '\t  Match the firmware-only SELinux load hooks of stock sheng 5.15.\n'
                     '\t  Normal file/sysfs access, other LSMs, and module load checks remain.\n')
receipt.write_text(json.dumps(dict(
    before=hashlib.sha256(before.encode()).hexdigest(), after=hashlib.sha256(after.encode()).hexdigest(),
    hardware_evidence='wrapped-r16 43.638825s kernel->kernel system:firmware_load denial prevents ueventd fallback; modem_a is already mounted at 39.886148s',
    firmware_present='/root/sheng-lineage/firmware-dump/hardware/firmware-files/modem/image/kiwi/amss20.bin',
    stock_ueventd_directories=['/apex/com.xiaomi.wifi/etc/firmware/', '/vendor/firmware_mnt/image/', '/apex/com.xiaomi.wifi/etc/'],
    scope='Only READING_FIRMWARE and LOADING_FIRMWARE SELinux load-hook checks match 5.15. Normal file/sysfs access checks, all other load classes, and other LSM/IMA hooks remain.',
    references=[dict(commit='ff4a6c3bb0f471a9dd186293a47b62c83829b97d', path='security/selinux/hooks.c', behavior='6.18 adds firmware_load check in file and data hooks'),
                dict(commit='f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d', path='security/selinux/hooks.c', behavior='5.15 SELinux read/load hooks only handle modules'),
                dict(commit='29db5d592c5b577aa9d9611da988a5e071d100dd', path='security/selinux/hooks.c', behavior='MiCode 5.15 has same firmware contract')],
    changes_stock_firmware=False, selinux_enforcing_retained=True), indent=2) + '\n')

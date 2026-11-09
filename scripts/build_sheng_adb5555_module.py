#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the user-authorized ADB startup module under WSL Python 3.11."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / 'device/xiaomi/sheng/tools/Adb5555Module'
OUTPUT = PROJECT / 'artifacts/sheng-adb-5555-v1'
REPORT = PROJECT / 'reports/sheng-adb-5555-module-v1.json'
FILES = ('module.prop', 'customize.sh', 'service.sh', 'worker.sh', 'restore.sh', 'uninstall.sh')

policy = json.loads((PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/root-policy.json').read_text())
assert policy['adb_startup_module_authorized'], 'User has not authorized this module'
assert policy['future_requested_adb_module_port'] == 5555
previous = json.loads(REPORT.read_text()) if REPORT.is_file() else {}
assert previous.get('install_result') != 'installed', 'Preserve the installed artifact'
payloads = {name: (SOURCE / name).read_bytes() for name in FILES}
hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
allowed_properties = {'service.adb.tcp.port', 'service.adb.listen_addrs', 'ctl.restart'}
for name, data in payloads.items():
    assert b'\r' not in data, name
    if name.endswith('.sh'):
        subprocess.run(['sh', '-n', SOURCE / name], check=True)
        assert set(re.findall(r'\bsetprop\s+(\S+)', data.decode())) <= allowed_properties

OUTPUT.mkdir(exist_ok=True)
archive = OUTPUT / 'sheng-adb-5555-v1.zip'
with zipfile.ZipFile(archive, 'w') as packed:
    for name, data in sorted(payloads.items()):
        entry = zipfile.ZipInfo(name, date_time=(2026, 11, 9, 0, 0, 0))
        entry.create_system = 3
        entry.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
        entry.compress_type = zipfile.ZIP_DEFLATED
        packed.writestr(entry, data)
with zipfile.ZipFile(archive) as packed:
    assert set(packed.namelist()) == set(FILES)
    for name, data in payloads.items():
        assert packed.read(name) == data
        assert (packed.getinfo(name).external_attr >> 16) & 0o777 == (0o755 if name.endswith('.sh') else 0o644)

report = dict(module='sheng_adb_5555', version='1.0', date='2026-11-09', port=5555,
              user_authorized=True, archive=str(archive.relative_to(PROJECT)),
              archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
              source_sha256=hashes, shell_syntax_checked=True,
              zip_payload_and_permissions_checked=True, built_in_gki_root_added=False,
              adb_authentication_unchanged=True, selinux_mode_unchanged=True,
              persistent_adb_properties_written=False, watch_interval_seconds=15,
              install_result='pending device connection', boot_autostart_verified=False,
              references=[
                  dict(repository='Android-packages-modules-adb', commit='f83360242ba6a66ae7570e126009ab530eeef120',
                       file='daemon/main.cpp', applicability='Existing runtime listen-address/port properties'),
                  dict(repository='KernelSU userspace reference only', commit='0c0fdb960178fa12d80d6cbcfdcb6ad8be6a865d',
                       files=['userspace/ksud/src/module.rs', 'userspace/ksud/src/installer.sh'],
                       applicability='Root-level module.prop/customize.sh/service.sh archive contract; no kernel integration'),
                  dict(repository='LineageOS-piano', commit='3f10fc25273b42d18d0bd533551a0a5c3dda0094',
                       applicability='Device tree does not provide a root startup-module recipe'),
                  dict(repository='LineageOS-nuwa', commit='8e2b6ca4375919035587115189760eed64f14b8d',
                       applicability='Device-specific tree does not provide a root startup-module recipe')],
              limitation='Host checks do not prove Android property access, actual listener availability or boot execution')
if previous.get('source_sha256') == hashes:
    for key in ('host_control_flow_checks', 'control_flow_check_scope'):
        if key in previous:
            report[key] = previous[key]
REPORT.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

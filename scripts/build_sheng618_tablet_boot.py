#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the N81A timing sequence plus the selected upstream legacy FastRPC port."""
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from build_sheng618_upstream import CLANG, K618, OUT, PROJECT, ROOT, UPSTREAM, command, environment
from audit_kernel618_modules import ElfModule, check_candidate
from audit_sheng618_overlay import audit, entries

tag = 'tablet-r20'
assert not (PROJECT / ('artifacts/sheng-6.18-' + tag)).exists()
source_report = json.loads((PROJECT / 'reports/kernel618-panel-timing-source.json').read_text())
display = K618 / 'vendor/qcom/opensource/display-drivers'
for name, hashes in source_report['files'].items():
    assert hashlib.sha256((display / name).read_bytes()).hexdigest() == hashes['after'], name
command(tag + '-display', ['bash', UPSTREAM / 'kernel-6.18/k618_tp.sh',
                          str(os.cpu_count()), 'display'], environment(os.cpu_count()))

# This removal of obsolete ION CMA handling is valid only after checking the
# actual tablet DT. Never assume the phone's board description is the same.
dt = ROOT / 'diagnostic/disklog-r5/live.dts'
assert 'qcom,msm-ion' not in dt.read_text()
command(tag + '-rpc515', ['bash', UPSTREAM / 'kernel-6.18/k618_rpc515.sh', str(os.cpu_count())],
        environment(os.cpu_count()))
rpc = K618 / 'vendor/xiaomi/adsprpc-515'
fuxi = K618 / 'src/fuxi'
assert subprocess.check_output(['git', '-C', fuxi, 'rev-parse', 'HEAD'], text=True).strip() == '7fad87dc178d09489b74a714e4a525d56f546855'
assert subprocess.check_output(['git', '-C', UPSTREAM, 'rev-parse', 'HEAD'], text=True).strip() == 'c3956156ce7c4193c451dfda531fad72d35bfebb'
files = ['adsprpc.c', 'adsprpc_compat.c', 'adsprpc_compat.h', 'adsprpc_shared.h',
         'adsprpc_rpmsg.c', 'adsprpc_socket.c', 'include/uapi/misc/fastrpc.h',
         'include/uapi/linux/msm_ion.h', 'include/uapi/linux/msm_ion_ids.h',
         'include/linux/qcom-dma-mapping.h', 'include/linux/fastrpc.h',
         'include/trace/events/fastrpc.h']
patch, hashes = [], {}
for name in files:
    oldpath = fuxi / (name if name.startswith('include/') else 'drivers/char/' + name)
    old, new = oldpath.read_bytes(), (rpc/name).read_bytes()
    hashes[name] = dict(before=hashlib.sha256(old).hexdigest(), after=hashlib.sha256(new).hexdigest())
    if old != new:
        patch.extend(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                     fromfile='a/'+name, tofile='b/'+name, n=3))
patchpath = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/legacy-fastrpc.patch'
patchpath.write_text(''.join(patch))
shutil.copyfile(rpc/'Kbuild', patchpath.parent/'legacy-fastrpc.Kbuild')
rpc_report = dict(
    upstream_repository='https://github.com/JiaqiLi404/android_kernel_618_for_sm8550',
    upstream_revision='c3956156ce7c4193c451dfda531fad72d35bfebb',
    source_revision='7fad87dc178d09489b74a714e4a525d56f546855',
    source_repository=subprocess.check_output(['git', '-C', fuxi, 'remote', 'get-url', 'origin'], text=True).strip(),
    upstream_scripts={n: hashlib.sha256((UPSTREAM/'kernel-6.18'/n).read_bytes()).hexdigest()
                      for n in ['k618_rpc515.sh', 'k618_rpc515_fix.py']},
    files=hashes, live_dt_sha256=hashlib.sha256(dt.read_bytes()).hexdigest(),
    live_dt_has_legacy_ion=False,
    compatibility='Original qcom,msm-fastrpc-compute binding and adsprpc-smd userspace nodes',
    matching_eva_rebuilt_with_legacy_header=True,
    hardware_result='pending', sensors_or_audio_fixed_claimed=False)
(PROJECT/'reports/kernel618-legacy-fastrpc-source.json').write_text(json.dumps(rpc_report, indent=2)+'\n')

native = ROOT / 'diagnostic' / tag
rd = native / 'layer'
shutil.copytree(ROOT / 'diagnostic/panel-r19/layer', rd, dirs_exist_ok=True)
modules = rd / 'lib/modules'
changed_modules = ['frpc-adsprpc.ko', 'msm-eva.ko', 'msm_drm.ko']
for name in changed_modules:
    shutil.copyfile(K618/'tpmods'/name, modules/name)
    subprocess.run([CLANG/'llvm-strip', '--strip-debug', modules/name], check=True)
checked = check_candidate({p.name: ElfModule(p) for p in modules.glob('*.ko')},
                         {'source_keep_modules': ['zram.ko', 'zsmalloc.ko']}, OUT,
                         [modules/'zram.ko', modules/'zsmalloc.ko'], '6.18')
assert checked['abi_passed'], checked['issue_counts']
overlay = native / 'overlay.cpio'
names = sorted(p.relative_to(rd).as_posix() for p in rd.rglob('*'))
with overlay.open('wb') as stream:
    subprocess.run(['cpio', '--null', '-o', '-H', 'newc', '-R', '0:0', '--quiet'],
                   input=('\0'.join(names)+'\0').encode(), cwd=rd, stdout=stream, check=True)
packed = {name: (mode, data) for name, mode, data in entries(overlay.read_bytes())}
baseline = {name: (mode, data) for name, mode, data in entries(
    (ROOT/'diagnostic/panel-r19/overlay.cpio').read_bytes())}
assert packed.keys() == baseline.keys()
assert all(packed[n][0] == baseline[n][0] for n in baseline)
changed = sorted(n for n in baseline if packed[n][1] != baseline[n][1])
assert changed == ['lib/modules/'+n for n in changed_modules], changed
metadata = audit(overlay)
assert metadata['helper_executable'] and metadata['module_count'] == 338
report = dict(revision=tag, checks=checked, archive=metadata, changed_payloads=changed,
              source_receipts=['kernel618-panel-timing-source.json', 'kernel618-legacy-fastrpc-source.json'],
              test_mode_enabled=False, hardware_result='pending')
(PROJECT/('reports/kernel618-'+tag+'-layer.json')).write_text(json.dumps(report, indent=2)+'\n')
subprocess.run([sys.executable, PROJECT/'scripts/build_sheng618_disklog_boot.py',
                '--tag', tag, '--overlay', overlay, '--legacy-module-reuse', '--legacy-fscrypt',
                '--legacy-firmware-lsm'], check=True)

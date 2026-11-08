#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build N81A DSC correction on the USB-r18 layer, with test reset disabled."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from build_sheng618_upstream import CLANG, K618, OUT, PROJECT, ROOT, UPSTREAM, command, environment
from audit_kernel618_modules import ElfModule, check_candidate
from audit_sheng618_overlay import audit, entries

tag = 'panel-r19'
assert not (PROJECT / ('artifacts/sheng-6.18-' + tag)).exists()
subprocess.run([sys.executable, PROJECT / 'scripts/patch_sheng618_panel_dsc.py'], check=True)
command(tag + '-module', ['bash', UPSTREAM / 'kernel-6.18/k618_tp.sh',
                          str(os.cpu_count()), 'display'], environment(os.cpu_count()))
native = ROOT / 'diagnostic' / tag
rd = native / 'layer'
shutil.copytree(ROOT / 'diagnostic/usb-r18/layer', rd, dirs_exist_ok=True)
modules = rd / 'lib/modules'
shutil.copyfile(K618 / 'tpmods/msm_drm.ko', modules / 'msm_drm.ko')
subprocess.run([CLANG / 'llvm-strip', '--strip-debug', modules / 'msm_drm.ko'], check=True)
checked = check_candidate({p.name: ElfModule(p) for p in modules.glob('*.ko')},
                         {'source_keep_modules': ['zram.ko', 'zsmalloc.ko']}, OUT,
                         [modules / 'zram.ko', modules / 'zsmalloc.ko'], '6.18')
assert checked['abi_passed'], checked['issue_counts']
overlay = native / 'overlay.cpio'
names = sorted(p.relative_to(rd).as_posix() for p in rd.rglob('*'))
with overlay.open('wb') as stream:
    subprocess.run(['cpio', '--null', '-o', '-H', 'newc', '-R', '0:0', '--quiet'],
                   input=('\0'.join(names)+'\0').encode(), cwd=rd, stdout=stream, check=True)
packed = {name: (mode, data) for name, mode, data in entries(overlay.read_bytes())}
baseline = {name: (mode, data) for name, mode, data in entries(
    (ROOT / 'diagnostic/usb-r18/overlay.cpio').read_bytes())}
assert packed.keys() == baseline.keys()
assert all(packed[n][0] == baseline[n][0] for n in baseline)
changed = sorted(n for n in baseline if packed[n][1] != baseline[n][1])
assert changed == ['lib/modules/msm_drm.ko'], changed
metadata = audit(overlay)
assert metadata['helper_executable'] and metadata['module_count'] == 338
report = dict(revision=tag, checks=checked, archive=metadata,
              changed_payloads=changed, source_receipt='kernel618-panel-dsc-source.json',
              msm_drm_sha256=hashlib.sha256((modules / 'msm_drm.ko').read_bytes()).hexdigest(),
              test_mode_disabled_because='usb-r18 candidate 6.18 ADB connected on hardware',
              hardware_result='pending')
(PROJECT / ('reports/kernel618-' + tag + '-layer.json')).write_text(json.dumps(report, indent=2) + '\n')
subprocess.run([sys.executable, PROJECT / 'scripts/build_sheng618_disklog_boot.py',
                '--tag', tag, '--overlay', overlay, '--legacy-module-reuse', '--legacy-fscrypt',
                '--legacy-firmware-lsm'], check=True)

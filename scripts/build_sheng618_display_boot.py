#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild the corrected display module, verify the whole layer, retain disk logs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from audit_kernel618_modules import ElfModule, check_candidate
from audit_sheng618_overlay import audit, entries
from build_sheng618_upstream import CLANG, K618, OUT, PROJECT, ROOT, UPSTREAM, command, environment

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', choices=['display-r6', 'display-r7'], default='display-r7')
parser.add_argument('--reuse-module', action='store_true',
                    help='Reuse the exact display module already verified for r6')
parser.add_argument('--replace-untested', action='store_true')
options = parser.parse_args()
tag = options.tag
native = ROOT / 'diagnostic' / tag
if (PROJECT / 'artifacts' / ('sheng-6.18-' + tag)).exists():
    assert options.replace_untested
    assert not (PROJECT / ('reports/device/kernel618-' + tag) / 'flash.txt').exists()
    assert not (PROJECT / ('reports/kernel618-' + tag + '-hardware.json')).exists()
native.mkdir(parents=True, exist_ok=True)
env = environment(os.cpu_count())
subprocess.run([sys.executable, PROJECT / 'scripts/patch_sheng618_display.py'], check=True)
if not options.reuse_module:
    command(tag + '-module', ['bash', UPSTREAM / 'kernel-6.18/k618_tp.sh',
                             str(os.cpu_count()), 'display'], env)
source_report = json.loads((PROJECT / 'reports/kernel618-display-multitiming-source.json').read_text())
tree = K618 / 'vendor/qcom/opensource/display-drivers'
for relative, hashes in source_report['files'].items():
    assert hashlib.sha256((tree / relative).read_bytes()).hexdigest() == hashes['after']

rd = native / 'layer'
old = K618 / 'boot-test/stage/rd'
shutil.copytree(old / 'lib', rd / 'lib', dirs_exist_ok=True)
shutil.copyfile(old / 'k618_umh', rd / 'k618_umh')
shutil.copymode(old / 'k618_umh', rd / 'k618_umh')
modules = rd / 'lib/modules'
replacement = K618 / 'tpmods/msm_drm.ko'
old_sha = hashlib.sha256((modules / 'msm_drm.ko').read_bytes()).hexdigest()
shutil.copyfile(replacement, modules / replacement.name)
# Match the original embedded layer's packaging: debug sections belong in the
# native build tree, not in a bootloader-constrained boot image.
subprocess.run([CLANG / 'llvm-strip', '--strip-debug', modules / replacement.name], check=True)
if options.reuse_module:
    r6 = json.loads((PROJECT / 'reports/kernel618-display-r6-layer.json').read_text())
    assert hashlib.sha256((modules / replacement.name).read_bytes()).hexdigest() == r6['new_msm_drm_sha256']
command(tag + '-layer-crc', ['python3', UPSTREAM / 'kernel-6.18/k618_stage_crc.py',
                            OUT / 'Module.symvers', modules], env)
checked = check_candidate({p.name: ElfModule(p) for p in modules.glob('*.ko')},
                          {'source_keep_modules': ['zram.ko', 'zsmalloc.ko']}, OUT,
                          [modules / 'zram.ko', modules / 'zsmalloc.ko'], '6.18')
assert checked['abi_passed'], checked['issue_counts']
listed = {Path(line.split(':', 1)[0]).name for line in (modules / 'modules.dep').read_text().splitlines()}
assert listed == {p.name for p in modules.glob('*.ko')}
overlay = native / 'overlay.cpio'
with overlay.open('wb') as stream:
    # mkbootfs applies Android fs_config defaults and silently makes an unknown
    # root executable 0644. Match upstream's newc cpio packing, preserving modes.
    names = sorted(p.relative_to(rd).as_posix() for p in rd.rglob('*'))
    subprocess.run(['cpio', '--null', '-o', '-H', 'newc', '-R', '0:0', '--quiet'],
                   input=('\0'.join(names) + '\0').encode(), cwd=rd,
                   stdout=stream, check=True)
original = {name: (mode, data) for name, mode, data in
            entries((K618 / 'boot-test/stage/overlay.cpio').read_bytes())}
packed = {name: (mode, data) for name, mode, data in entries(overlay.read_bytes())}
assert original.keys() == packed.keys()
assert all(original[name][0] == packed[name][0] for name in original), 'Archive modes changed'
changed = sorted(name for name in original if original[name][1] != packed[name][1])
assert changed == ['lib/modules/msm_drm.ko'], changed
metadata = audit(overlay)
assert metadata['helper_executable'] and metadata['helper_mode'] == '0o100755'
report = {'revision': tag, 'checks': checked, 'old_msm_drm_sha256': old_sha,
          'new_msm_drm_sha256': hashlib.sha256((modules / 'msm_drm.ko').read_bytes()).hexdigest(),
          'module_count': len(list(modules.glob('*.ko'))), 'dependency_coverage': True,
          'source_receipt': 'kernel618-display-multitiming-source.json',
          'overlay_sha256': hashlib.sha256(overlay.read_bytes()).hexdigest(),
          'archive_metadata': metadata, 'changed_payloads': changed,
          'all_archive_modes_match_original': True,
          'reused_verified_display_module': options.reuse_module,
          'hardware_result': 'pending'}
(PROJECT / ('reports/kernel618-' + tag + '-layer.json')).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
subprocess.run([sys.executable, PROJECT / 'scripts/build_sheng618_disklog_boot.py',
                '--tag', tag, '--overlay', overlay,
                *(['--replace-untested'] if options.replace_untested else [])], env=env, check=True)

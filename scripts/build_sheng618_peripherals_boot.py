#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package a preserved tablet layer with native THP/pen and six-amp routing."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from build_sheng618_upstream import CLANG, K618, OUT, PROJECT, ROOT
from audit_kernel618_modules import ElfModule, check_candidate
from audit_sheng618_overlay import audit, entries

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', default='peripherals-r21')
parser.add_argument('--base', choices=['tablet-r20', 'peripherals-r21'], default='tablet-r20')
parser.add_argument('--replace-untested', action='store_true')
options = parser.parse_args()
import re
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.tag)
tag = options.tag
native = ROOT/'diagnostic'/tag
rd = native/'layer'
delivery = PROJECT/('artifacts/sheng-6.18-'+tag)
assert not delivery.exists() or options.replace_untested, 'Preserve existing candidate'
if options.replace_untested:
    assert not (PROJECT/('reports/kernel618-'+tag+'-hardware.json')).exists()
    assert not (PROJECT/('reports/device/kernel618-'+tag)/'flash.txt').exists()
base = ROOT/'diagnostic'/options.base/'layer'
shutil.copytree(base, rd, dirs_exist_ok=True)
modules = rd/'lib/modules'
replacements = {
    'qti_battery_charger.ko': K618/'soc/qti_battery_charger.ko',
    'msm_drm.ko': K618/'vendor/qcom/opensource/display-drivers/msm/msm_drm.ko',
    'machine_dlkm.ko': K618/'vendor/qcom/opensource/audio-kernel/asoc/machine_dlkm.ko',
    'xiaomi_touch.ko': K618/'sheng-ports/touch/xiaomi_touch.ko',
    'nt36532_touch.ko': K618/'sheng-ports/touch/nt36532_touch.ko',
}
source_receipts = ['kernel618-peripherals-source.json','kernel618-touch-source.json']
followup = PROJECT/'reports/kernel618-camera-backlight-source.json'
if followup.exists():
    source_receipts.append(followup.name)
    replacements['camera.ko'] = K618/'vendor/qcom/opensource/camera-kernel/camera.ko'
extra_groups = {
    'fingerprint': ('fpc1552.ko', 'xiaomifp.ko'),
    'hall': ('xiaomi_hall.ko',),
}
for group, names in extra_groups.items():
    receipt = PROJECT/'reports'/('kernel618-'+group+'-source.json')
    if not receipt.exists():
        continue
    source_receipts.append(receipt.name)
    data = json.loads(receipt.read_text())
    for name, hashes in data['files'].items():
        assert hashlib.sha256((K618/'sheng-ports'/group/name).read_bytes()).hexdigest() == hashes['staged_sha256'], name
    replacements.update({name: K618/'sheng-ports'/group/name for name in names})
source_snapshots = {}
for receipt_name in source_receipts:
    source_snapshots[receipt_name] = json.loads((PROJECT/'reports'/receipt_name).read_text())
expected_sources = {name: hashes['after'] for name, hashes in source_snapshots['kernel618-peripherals-source.json']['files'].items()}
if followup.exists():
    for name, hashes in source_snapshots[followup.name]['files'].items():
        if name in expected_sources:
            assert hashes['before'] == expected_sources[name], 'Source chain mismatch: ' + name
        expected_sources[name] = hashes['after']
for name, expected in expected_sources.items():
    assert hashlib.sha256((K618/name).read_bytes()).hexdigest() == expected, name
for name, hashes in json.loads((PROJECT/'reports/kernel618-touch-source.json').read_text())['files'].items():
    assert hashlib.sha256((K618/'sheng-ports/touch'/name).read_bytes()).hexdigest() == hashes['staged_sha256'], name
for name, source in replacements.items():
    shutil.copyfile(source, modules/name)
    subprocess.run([CLANG/'llvm-strip','--strip-debug',modules/name],check=True)
checked = check_candidate({p.name:ElfModule(p) for p in modules.glob('*.ko')},
    {'source_keep_modules':['zram.ko','zsmalloc.ko']},OUT,
    [modules/'zram.ko',modules/'zsmalloc.ko'],'6.18')
assert checked['abi_passed'], checked['issue_counts']

# Use depmod's actual symbol graph, including transitive loader dependencies.
release = (OUT/'include/config/kernel.release').read_text().strip()
dep_root = native/'depmod-root'
target = dep_root/'lib/modules'/release
kernel = target/'kernel'
kernel.mkdir(parents=True,exist_ok=True)
for module in modules.glob('*.ko'):
    dest = kernel/module.name
    if dest.exists():
        dest.unlink()
    os.link(module,dest)
for name in ('modules.builtin','modules.builtin.modinfo'):
    shutil.copyfile(OUT/name,target/name)
(target/'modules.order').write_text(''.join('kernel/'+name+'\n' for name in sorted(replacements)))
result = subprocess.run(['depmod','-b',dep_root,'-F',OUT/'System.map','-e',release],capture_output=True,text=True)
assert result.returncode == 0 and not result.stderr.strip(),result.stderr
for name in ('modules.dep','modules.alias','modules.softdep'):
    data = (target/name).read_text().replace('kernel/','/lib/modules/')
    (modules/name).write_text(data)
load = modules/'k618_batch.load'
text = load.read_text()
late_modules = [name for names in extra_groups.values() for name in names if name in replacements]
late_modules += ['xiaomi_touch.ko', 'nt36532_touch.ko']
lines = [line for line in text.splitlines() if line not in late_modules]
load.write_text('\n'.join(lines + late_modules)+'\n')
assert load.read_text().splitlines()[-len(late_modules):] == late_modules

overlay = native/'overlay.cpio'
names = sorted(p.relative_to(rd).as_posix() for p in rd.rglob('*'))
with overlay.open('wb') as stream:
    subprocess.run(['cpio','--null','-o','-H','newc','-R','0:0','--quiet'],
        input=('\0'.join(names)+'\0').encode(),cwd=rd,stdout=stream,check=True)
packed = {name:(mode,data) for name,mode,data in entries(overlay.read_bytes())}
baseline = {name:(mode,data) for name,mode,data in entries((ROOT/'diagnostic'/options.base/'overlay.cpio').read_bytes())}
assert all(packed[n][0] == baseline[n][0] for n in baseline)
added = sorted(packed.keys()-baseline.keys())
expected_added = sorted('lib/modules/'+n for n in replacements
                        if 'lib/modules/'+n not in baseline)
assert added == expected_added,added
changed = sorted(n for n in baseline if packed[n][1] != baseline[n][1])
allowed = {'lib/modules/'+name for name in replacements}
allowed |= {'lib/modules/'+name for name in ['modules.dep','modules.alias','modules.softdep','k618_batch.load']}
assert set(changed) <= allowed, changed
metadata = audit(overlay)
expected_count = sum(name.endswith('.ko') for name in baseline) + len(expected_added)
assert metadata['helper_executable'] and metadata['module_count'] == expected_count
report = dict(revision=tag,base_revision=options.base,checks=checked,archive=metadata,
    changed_payloads=changed,added_payloads=added,source_receipts=source_receipts,
    source_snapshots=source_snapshots,
    replacement_module_sha256={name:hashlib.sha256((modules/name).read_bytes()).hexdigest()
                               for name in replacements},
    test_mode_enabled=False,hardware_result='pending')
(PROJECT/('reports/kernel618-'+tag+'-layer.json')).write_text(json.dumps(report,indent=2)+'\n')
args = [sys.executable,PROJECT/'scripts/build_sheng618_disklog_boot.py',
    '--tag',tag,'--overlay',overlay,'--legacy-module-reuse','--legacy-fscrypt','--legacy-firmware-lsm']
if options.replace_untested:
    args.append('--replace-untested')
subprocess.run(args,check=True)

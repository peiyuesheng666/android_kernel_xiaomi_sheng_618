#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package the verified r20 layer with native THP/pen and six-amp routing."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from build_sheng618_upstream import CLANG, K618, OUT, PROJECT, ROOT
from audit_kernel618_modules import ElfModule, check_candidate
from audit_sheng618_overlay import audit, entries

tag = 'peripherals-r21'
native = ROOT/'diagnostic'/tag
rd = native/'layer'
delivery = PROJECT/('artifacts/sheng-6.18-'+tag)
assert not delivery.exists(), 'Preserve existing candidate'
base = ROOT/'diagnostic/tablet-r20/layer'
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
for name, hashes in json.loads((PROJECT/'reports/kernel618-peripherals-source.json').read_text())['files'].items():
    assert hashlib.sha256((K618/name).read_bytes()).hexdigest() == hashes['after'], name
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
assert 'xiaomi_touch.ko' not in text and 'nt36532_touch.ko' not in text
load.write_text(text.rstrip()+'\nxiaomi_touch.ko\nnt36532_touch.ko\n')
assert (modules/'k618_batch.load').read_text().splitlines()[-2:] == ['xiaomi_touch.ko','nt36532_touch.ko']

overlay = native/'overlay.cpio'
names = sorted(p.relative_to(rd).as_posix() for p in rd.rglob('*'))
with overlay.open('wb') as stream:
    subprocess.run(['cpio','--null','-o','-H','newc','-R','0:0','--quiet'],
        input=('\0'.join(names)+'\0').encode(),cwd=rd,stdout=stream,check=True)
packed = {name:(mode,data) for name,mode,data in entries(overlay.read_bytes())}
baseline = {name:(mode,data) for name,mode,data in entries((ROOT/'diagnostic/tablet-r20/overlay.cpio').read_bytes())}
assert all(packed[n][0] == baseline[n][0] for n in baseline)
added = sorted(packed.keys()-baseline.keys())
assert added == ['lib/modules/nt36532_touch.ko','lib/modules/xiaomi_touch.ko'],added
changed = sorted(n for n in baseline if packed[n][1] != baseline[n][1])
allowed = {'lib/modules/'+name for name in replacements}
allowed |= {'lib/modules/'+name for name in ['modules.dep','modules.alias','modules.softdep','k618_batch.load']}
assert set(changed) <= allowed, changed
metadata = audit(overlay)
assert metadata['helper_executable'] and metadata['module_count'] == 340
report = dict(revision=tag,base_revision='tablet-r20',checks=checked,archive=metadata,
    changed_payloads=changed,added_payloads=added,source_receipts=source_receipts,
    test_mode_enabled=False,hardware_result='pending')
(PROJECT/('reports/kernel618-'+tag+'-layer.json')).write_text(json.dumps(report,indent=2)+'\n')
subprocess.run([sys.executable,PROJECT/'scripts/build_sheng618_disklog_boot.py',
    '--tag',tag,'--overlay',overlay,'--legacy-module-reuse','--legacy-fscrypt','--legacy-firmware-lsm'],check=True)

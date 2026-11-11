#!/usr/bin/env python3
"""Export verified r85 outputs, replay its patch, and read back source archive."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

workspace=Path(__file__).resolve().parents[1]
project=Path('/root/sheng-618-repair-r87-project')
build=Path('/root/sheng-618-repair-r86-build')
base=Path('/root/sheng-618-pen-release-build')
delivery=workspace/'artifacts/sheng-6.18-repair-r87'
sha=lambda p: hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
receipt=json.loads((project/'provenance/repair-r85.json').read_text())
pps_test=json.loads((workspace/'reports/kernel618-pps-auto-r87-tests.json').read_text())
assert pps_test['passed'] and pps_test['stable_grace_seconds']==0
assert receipt['pps_auto_policy']['immediate_after_confirmed_recognition']
validation=json.loads((project/'dist/repair-r87/validation.json').read_text())
btf=json.loads((workspace/'reports/kernel618-repair-r87-btf.json').read_text())
assert btf['all_modules_parsed_against_final_kernel'] and btf['distilled_modules_verified']
assert validation['fresh_build_verified'] and validation['module_abi']['abi_passed']
assert validation['build']['boot_packaged'] and validation['module_count']==344
assert validation['build_profile']['mode']=='release'
assert not validation['build_profile']['rawdump_enabled']
with tempfile.TemporaryDirectory(prefix='sheng-r87-replay-',dir='/root') as temp:
    replay=Path(temp)
    for name, hashes in receipt['files'].items():
        old=base/name
        assert (sha(old) if old.exists() else None)==hashes['before'],name
        if old.exists():
            (replay/name).parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(old,replay/name)
    env=dict(os.environ,PROJECT_ROOT=str(project),BUILD_ROOT=str(replay))
    subprocess.run(['python3.11',str(project/'scripts/apply-repair-r85.py')],env=env,check=True)
    subprocess.run(['python3.11',str(project/'scripts/apply-repair-r85.py'),'--check'],env=env,check=True)
    for name,hashes in receipt['files'].items():assert sha(replay/name)==hashes['after']
assert not delivery.exists(), 'Preserve prior delivery'
delivery.mkdir()
for name in ('Image','boot.img','build-result.json','validation.json'):
    src=project/'dist/repair-r87'/name
    shutil.copyfile(src,delivery/name)
    assert sha(src)==sha(delivery/name)
assert (delivery/'boot.img').stat().st_size==201326592
assert sha(delivery/'boot.img')==validation['build']['artifacts']['boot.img']
shutil.copyfile(workspace/'reports/kernel618-repair-r87-btf.json',delivery/'btf-validation.json')
shutil.copyfile(project/'provenance/repair-r85.json',delivery/'repair-r87.json')
for name in ('kernel618-charging-interfaces-r85-tests.json','kernel618-charging-special-r85-tests.json','kernel618-pps-auto-r87-tests.json'):
    shutil.copyfile(workspace/'reports'/name,delivery/name)
intro='# sheng Linux 6.18.32 · repair r87\n\n基于r76，保留r86的57个充电接口、旁路属性219与32 ms笔触滤波。\nr86实机追踪确认batterysecret认证结束后写pd_verifed=0，旧版抑制规则阻止恢复。\nr87自动模式下sysfs写0立即触发重新判断；verify_process非0期间优先原厂认证。\n非零adapter_id与身份不明/小米SVID的>=100 W能力均保留原厂识别路径。\n真实在线PPS、SNK_Ready、有效能力、双电池认证、Good健康且无input_suspend后立即写1。\n首写没有固定等待；已接PPS的5秒freezable读取兜底监测固件回0，sysfs/通知即时触发。\n已有1不重写；成功清零连续失败预算，连续失败最多3次；参数N可禁用自动写入。\n不伪造90/120 W，不修改电流/温控；动画过渡仍需新内核实机验收。\n无法明确区分身份的>=100 W第三方源仍保守保留认证流程，此边界未证明全部第三方覆盖。\n57节点在r86实机全部存在且读取成功；旁路供电及r87笔休眠恢复尚需实测。\n风驰继续暂停，不加载实验调度模块。\n\n此项目复用r86绝对路径的可变构建缓存；r86原交付/源码归档保留。\n最终源码由固定哈希基线缓存、既有补丁及patches/sheng-repair-r87.patch组合构成。\n完整差异及文件哈希见provenance/repair-r85.json（revision=repair-r87）。\n\n'
path=project/'README.zh-CN.md'
inherited=path.read_text();anchor='# 小米平板 6S Pro · Linux 6.18.32'
assert inherited.count(anchor)==1
path.write_text(intro+inherited[inherited.index(anchor):])
path=project/'README.md';path.write_text('''# Sheng Linux 6.18.32 repair r87

Isolated r76-based charging interface repair. See README.zh-CN.md and
provenance/repair-r85.json for the 57 restored shipping interfaces, bounded
factory callbacks, source replay, and hardware validation limitations.
The source cache is the pinned baseline plus verified downstream patches.
The mutable build cache remains at the r86 absolute path; r86 artifacts are preserved.
See docs/FEATURES-REPAIR-r87.zh-CN.md for actual hardware evidence and boundaries.

'''+path.read_text())
subprocess.run(['python3.11',str(workspace/'scripts/package_sheng_release_snapshot.py'),
                '--project',str(project),'--tag','repair-r87'],check=True)
source=json.loads((delivery/'source-project-validation.json').read_text())
result=dict(revision='repair-r87',base='ipv6-release-r76',boot_sha256=sha(delivery/'boot.img'),
    boot_bytes=(delivery/'boot.img').stat().st_size,patch_replay_verified=True,
    archive_readback_verified=source['archive_readback_verified'],module_count=344,
    source_model='pinned baseline source cache + verified inherited patches + repair-r87 patch',
    hardware_verified=False,pps_default_override_added=True,pps_recognition_delay_seconds=0)
(delivery/'package-validation.json').write_text(json.dumps(result,indent=2)+'\n')
with (delivery/'SHA256SUMS').open('w') as stream:
    for path in sorted(delivery.iterdir()):
        if path.is_file() and path.name!='SHA256SUMS':stream.write(sha(path)+'  '+path.name+'\n')
print(json.dumps(result,indent=2),flush=True)

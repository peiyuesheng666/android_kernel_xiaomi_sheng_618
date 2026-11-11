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
project=Path('/root/sheng-618-repair-r86-project')
build=Path('/root/sheng-618-repair-r86-build')
base=Path('/root/sheng-618-pen-release-build')
delivery=workspace/'artifacts/sheng-6.18-repair-r86'
sha=lambda p: hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
receipt=json.loads((project/'provenance/repair-r85.json').read_text())
pps_test=json.loads((workspace/'reports/kernel618-pps-auto-r86-tests.json').read_text())
assert pps_test['passed'] and pps_test['stable_grace_seconds']==0
assert receipt['pps_auto_policy']['immediate_after_confirmed_recognition']
validation=json.loads((project/'dist/repair-r86/validation.json').read_text())
btf=json.loads((workspace/'reports/kernel618-repair-r86-btf.json').read_text())
assert btf['all_modules_parsed_against_final_kernel'] and btf['distilled_modules_verified']
assert validation['fresh_build_verified'] and validation['module_abi']['abi_passed']
assert validation['build']['boot_packaged'] and validation['module_count']==344
assert validation['build_profile']['mode']=='release'
assert not validation['build_profile']['rawdump_enabled']
with tempfile.TemporaryDirectory(prefix='sheng-r86-replay-',dir='/root') as temp:
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
    src=project/'dist/repair-r86'/name
    shutil.copyfile(src,delivery/name)
    assert sha(src)==sha(delivery/name)
assert (delivery/'boot.img').stat().st_size==201326592
assert sha(delivery/'boot.img')==validation['build']['artifacts']['boot.img']
shutil.copyfile(workspace/'reports/kernel618-repair-r86-btf.json',delivery/'btf-validation.json')
shutil.copyfile(project/'provenance/repair-r85.json',delivery/'repair-r86.json')
for name in ('kernel618-charging-interfaces-r85-tests.json','kernel618-charging-special-r85-tests.json','kernel618-pps-auto-r86-tests.json'):
    shutil.copyfile(workspace/'reports'/name,delivery/name)
intro='# sheng Linux 6.18.32 · repair r86\n\n基于r76与已校验r85的隔离工程。保留57个补齐的原厂充电接口、旁路属性219、\n32 ms笔触滤波、笔节点/uevent、双电池认证、IPv6 NAT与release行为。\n按用户最新要求，第三方PPS身份/能力确认完成后立即写pd_verifed=1，无固定等待。\n已有值1不重复写；非零原厂适配器ID或身份不明的120 W能力保留原识别流程；不单靠旧SVID判断。\n固件属性21=31(SNK_Ready)且能力有效后才算识别完成；未认证/不健康或输入暂停时不写。\n真实glink回读成功且连接仍是PPS才报成功；失败最多尝试三次，允许关闭自动逻辑。\n手动写0在当前已观察到的连接中优先，观察到断开后清除抑制状态。\n不修改电流或温控限制，不写假的功率值。\n源码和主机测试通过不等于华为90 W/小米120 W或旁路行为已实机通过。\n风驰保持暂停，本版不加载实验调度模块。\n\n固定哈希的基线源码缓存加既有补丁和patches/sheng-repair-r86.patch构成最终源码。\n完整组合差异/哈希记录在继承的provenance/repair-r85.json（revision=repair-r86）。\n最终BTF校验、344模块ABI、补丁回放和源码归档读回均是交付门槛。\n\n'
path=project/'README.zh-CN.md';path.write_text(intro+path.read_text())
path=project/'README.md';path.write_text('''# Sheng Linux 6.18.32 repair r85

Isolated r76-based charging interface repair. See README.zh-CN.md and
provenance/repair-r85.json for the 57 restored shipping interfaces, bounded
factory callbacks, source replay, and hardware validation limitations.
The source cache is the pinned baseline plus verified downstream patches.

'''+path.read_text())
subprocess.run(['python3.11',str(workspace/'scripts/package_sheng_release_snapshot.py'),
                '--project',str(project),'--tag','repair-r86'],check=True)
source=json.loads((delivery/'source-project-validation.json').read_text())
result=dict(revision='repair-r86',base='ipv6-release-r76',boot_sha256=sha(delivery/'boot.img'),
    boot_bytes=(delivery/'boot.img').stat().st_size,patch_replay_verified=True,
    archive_readback_verified=source['archive_readback_verified'],module_count=344,
    source_model='pinned baseline source cache + verified inherited patches + repair-r86 patch',
    hardware_verified=False,pps_default_override_added=True,pps_recognition_delay_seconds=0)
(delivery/'package-validation.json').write_text(json.dumps(result,indent=2)+'\n')
with (delivery/'SHA256SUMS').open('w') as stream:
    for path in sorted(delivery.iterdir()):
        if path.is_file() and path.name!='SHA256SUMS':stream.write(sha(path)+'  '+path.name+'\n')
print(json.dumps(result,indent=2),flush=True)

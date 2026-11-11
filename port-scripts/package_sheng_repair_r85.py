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
project=Path('/root/sheng-618-repair-r85-project')
build=Path('/root/sheng-618-repair-r85-build')
base=Path('/root/sheng-618-pen-release-build')
delivery=workspace/'artifacts/sheng-6.18-repair-r85'
sha=lambda p: hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
receipt=json.loads((project/'provenance/repair-r85.json').read_text())
validation=json.loads((project/'dist/repair-r85/validation.json').read_text())
btf=json.loads((workspace/'reports/kernel618-repair-r85-btf.json').read_text())
assert btf['all_modules_parsed_against_final_kernel'] and btf['distilled_modules_verified']
assert validation['fresh_build_verified'] and validation['module_abi']['abi_passed']
assert validation['build']['boot_packaged'] and validation['module_count']==344
assert validation['build_profile']['mode']=='release'
assert not validation['build_profile']['rawdump_enabled']
with tempfile.TemporaryDirectory(prefix='sheng-r85-replay-',dir='/root') as temp:
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
    src=project/'dist/repair-r85'/name
    shutil.copyfile(src,delivery/name)
    assert sha(src)==sha(delivery/name)
assert (delivery/'boot.img').stat().st_size==201326592
assert sha(delivery/'boot.img')==validation['build']['artifacts']['boot.img']
shutil.copyfile(workspace/'reports/kernel618-repair-r85-btf.json',delivery/'btf-validation.json')
shutil.copyfile(project/'provenance/repair-r85.json',delivery/'repair-r85.json')
for name in ('kernel618-charging-interfaces-r85-tests.json','kernel618-charging-special-r85-tests.json'):
    shutil.copyfile(workspace/'reports'/name,delivery/name)
intro='''# sheng Linux 6.18.32 · repair r85

基于 r76 的隔离工程，补齐原厂 qcom-battery 中缺失的 57 个充电接口，
其中 charging_suspend_battery 使用原厂属性 219。保留 r76 的 32 ms 笔触滤波、
笔节点/uevent、双电池认证、容器网络/IPv6 NAT 与 release 行为。
原厂模块反汇编核对编号、格式、parser 和特殊请求长度；所有新增节点访问真实
PMIC glink，不添加默认充电写入，不更改温控/电流保护。
未强制 pd_verifed：酷态科 15 Ultra + Apple C-to-C 实测已是 PD_PPS 且值为 1。
低电量功率、旁路供电和刷写后的笔触仍需单独实机验收，不能将节点存在视为通过。
风驰移植暂停，本版不加载实验性调度模块。

源码缓存仍为固定哈希的基线缓存；最终源码由既有补丁加
patches/sheng-repair-r85.patch 构成。provenance/repair-r85.json
记录完整 r76 → r85 差异，构建脚本和 verifier 校验所有修改文件哈希。

'''
path=project/'README.zh-CN.md';path.write_text(intro+path.read_text())
path=project/'README.md';path.write_text('''# Sheng Linux 6.18.32 repair r85

Isolated r76-based charging interface repair. See README.zh-CN.md and
provenance/repair-r85.json for the 57 restored shipping interfaces, bounded
factory callbacks, source replay, and hardware validation limitations.
The source cache is the pinned baseline plus verified downstream patches.

'''+path.read_text())
subprocess.run(['python3.11',str(workspace/'scripts/package_sheng_release_snapshot.py'),
                '--project',str(project),'--tag','repair-r85'],check=True)
source=json.loads((delivery/'source-project-validation.json').read_text())
result=dict(revision='repair-r85',base='ipv6-release-r76',boot_sha256=sha(delivery/'boot.img'),
    boot_bytes=(delivery/'boot.img').stat().st_size,patch_replay_verified=True,
    archive_readback_verified=source['archive_readback_verified'],module_count=344,
    source_model='pinned baseline source cache + verified inherited patches + repair-r85 patch',
    hardware_verified=False,pps_default_override_added=False)
(delivery/'package-validation.json').write_text(json.dumps(result,indent=2)+'\n')
with (delivery/'SHA256SUMS').open('w') as stream:
    for path in sorted(delivery.iterdir()):
        if path.is_file() and path.name!='SHA256SUMS':stream.write(sha(path)+'  '+path.name+'\n')
print(json.dumps(result,indent=2),flush=True)

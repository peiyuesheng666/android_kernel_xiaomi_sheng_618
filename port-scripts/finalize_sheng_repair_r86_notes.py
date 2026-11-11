#!/usr/bin/env python3
"""Preserve final immediate policy, firmware observations and current acceptance tools."""
from pathlib import Path
import shutil

workspace=Path(__file__).resolve().parents[1]
project=Path('/root/sheng-618-repair-r86-project')
path=workspace/'reports/kernel618-features-repair-r86.md';text=path.read_text()
old='''小米SVID0x2717、至少110 W的能力、已有值1或身份不明的非零adapter ID不被抢写；
华为SVID0x12d1允许走第三方路径。SVID/ID字段可能保留旧值，模糊情况保守跳过，需实机确认。'''
new='''已有值1保持不变；非零原厂adapter ID保留原有认证路径。
SVID未知或保留小米值时，至少110 W的能力仍保守跳过，以保护120 W识别。
实际华为对照读到SVID=2717但adapter ID=0、APDO/power_max=90；因此不会只凭旧SVID拒绝第三方。
固件属性21必须为31（SNK_Ready）且能力有效才算识别完成，随后立即写入，无固定等待。'''
if old in text:text=text.replace(old,new)
if '华为实机对照（r80）' not in text:
    text+='''

## 华为实机对照（r80）

日志：`logs/charging-huawei-before-r86-20261111-200506/`、
`logs/r85-pps-20261111-201027/`。用户确认连接华为100 W充电器。
未写前：PD_PPS、pd_verifed=0、APDO=90、power_max=90、adapter_id=0、
adapter_svid=2717、SNK_Ready。这个SVID不能视作当前充电器品牌。
临时写1后固件接受，采样完成恢复0；电量72～73%、温度约26℃。
充电泵总线估算约26 W。USB电流节点持续约72 mA，与充电泵/电池读数不一致，
不能把USB voltage_now × current_now当成可靠的实测输入功率。
充电泵估算也不是外部功率计测量；还需核对拓扑、低电量和线材。
这些数据验证了手动写1的固件回读，没有验证r86自动写入、90 W峰值或小米120 W显示。
'''
path.write_text(text)
shutil.copyfile(path,project/'docs/FEATURES-REPAIR-r86.zh-CN.md')
path=workspace/'scripts/package_sheng_repair_r86.py';text=path.read_text()
text=text.replace('小米SVID、120 W能力或不明厂商ID优先保留原识别流程。',
    '非零原厂适配器ID或身份不明的120 W能力保留原识别流程；不单靠旧SVID判断。')
text=text.replace('尚无有效能力信息、不健康/未认证电池或输入暂停时不自动写。',
    '固件属性21=31(SNK_Ready)且能力有效后才算识别完成；未认证/不健康或输入暂停时不写。')
path.write_text(text)
for name in ('package_sheng_repair_r86.py','verify_sheng_repair_r86_btf.py',
             'flash_sheng_repair_r86_wireless.py','check_sheng_repair_r86_nodes.py',
             'probe_sheng_bypass_r86.py','test_sheng_pps_auto_r86.py',
             'sync_sheng_pps_auto_r86.py','stage_sheng_pps_auto_r86.py',
             'prepare_sheng_repair_r86.py','finalize_sheng_repair_r86_notes.py',
             'capture_sheng_charging_wireless.py','probe_sheng_standard_pps_r85.py'):
    shutil.copyfile(workspace/'scripts'/name,project/'port-scripts'/name)
print('Final r86 notes include immediate policy, stale SVID and actual Huawei test limits',flush=True)

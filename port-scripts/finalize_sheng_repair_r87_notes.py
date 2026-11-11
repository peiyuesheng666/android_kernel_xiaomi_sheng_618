"""Document observed r86 failure and r87 implementation without claiming hardware success."""
from pathlib import Path
import shutil
import json
w=Path(__file__).resolve().parents[1]
p=Path('/root/sheng-618-repair-r87-project')
path=w/'reports/kernel618-features-repair-r86.md';s=path.read_text()
s=s.replace('默认强制认证机制尚未添加；\n若实际故障连接返回0，再检查认证来源与安全的连接状态处理。',
            'r86已实现条件自动认证，但实机发现系统随后写0，r87继续修复；\n+低SOC实际输入功率尚未验收。'.replace('\n+','\n'))
s=s.replace('实际厂商充电器识别时序与功率仍待刷入后验证。',
            'r86已无线刷入并正常启动；实机PPS失败事实与追踪见下方，不能按主机测试判通过。')
if '## r86 实机验收修正' not in s:
    s+='''

## r86 实机验收修正

r86已经无线刷入603ac302并正常启动，boot_a完整回读通过；init_boot_a保持原哈希。
报告：`kernel618-repair-r86-wireless-flash.json`。默认笔滤波32、PPS参数Y。
`kernel618-repair-r86-nodes.json`：57个补齐节点全部存在且读取成功，主副电池认证均1。
这是接口读取验收；旁路开关的真实电流变化、工厂节点语义仍不视为全部通过。

r86自动PPS实机验收失败。dmesg可见自动写1确实成功，数秒后回0；
原装充电器在SVID0、ID0、APDO100 W时也被提前接管。不能表述成“自动工作没有执行”。
私有kprobe追踪 `logs/pps-r87-trace-20261111-203944/trace.txt` 确认：
batterysecret进程7131写verify_process=1，在0.65秒后写verify_process=0，紧接着写pd_verifed=0。
这里只追踪开关首字符（49是ASCII 1，48是ASCII 0），不读取认证seed或digest。
r86将成功sysfs写0永久抑制本次连接，且成功写1消耗三次预算，导致不能恢复。
r86历史实现段中的110 W阈值与写0抑制规则仅代表旧版，r87替代逻辑见新报告。
'''
path.write_text(s)
prefix=s.split('## 构建、交付与待办')[0]
new=prefix+'''
## r87 自动PPS修复与边界

基于r76并继承r86的接口修复，风驰继续暂停。
实机追踪确认batterysecret认证结束后写pd_verifed=0，因此删除旧版“写0抑制整次连接”规则。
自动模式Y时，成功sysfs写入后立即重新检查；verify_process非0期间优先原厂认证。
verify_process写入和自动工作共享锁，并增加epoch，避免认证开始时继续用旧快照写1。

真实在线PD_PPS、SNK_Ready、有效APDO/power_max、主副电池认证与匹配1、Good健康、
无input_suspend后立即写属性24=1，首写没有固定等待。已有1不重写；成功不消耗失败预算。
成功写入后继续监测已接PPS，5秒freezable读取兜底捕捉固件自行清零；事件和sysfs即时触发，
这个监测周期不是识别后的等待。断开/非PPS停止周期监测，连续失败最多3次。
参数 `/sys/module/qti_battery_charger/parameters/sheng_pps_auto_verify` 写N可禁用自动写入。

非零adapter_id保留原认证；SVID未知或残留小米值且能力>=100 W时不接管，
覆盖已观察到的原装100→120 W阶段。华为真实样本ID0、残留SVID2717、APDO/power90允许解锁。
身份不明的>=100 W第三方源仍可能被保守跳过；不能声称覆盖所有第三方PPS。
不改充电电流/温控、不伪造功率动画字段。33 W/MI Turbo动画过渡需重插实机对照。

生产policy/snapshot/worker/store的ASan/UBSan测试通过，覆盖batterysecret顺序、
反复固件清零、已有1仅监测、原装100→120、健康/认证/暂停、连接/通知/禁用竞态与回读失败。
主机测试不能代替华为自动1持久、小米120动画、旁路双电池电流和笔休眠恢复验收。

## 构建、交付与实机记录

项目 `/root/sheng-618-repair-r87-project`；复用绝对路径不变的r86可变build缓存，
原r76/r80/r85/r86交付、源码归档与镜像保留。最终源码是固定哈希缓存加既有补丁与
`patches/sheng-repair-r87.patch`，receipt沿用 `provenance/repair-r85.json` 文件名，revision为repair-r87。
344模块ABI、最终BTF、源码校验、组合补丁回放和归档读回都是无线刷写门槛。
只写boot_a，保留init_boot_a与新鲜备份，只通过无线ADB操作603ac302。

r86已刷入：57节点全部读取成功，笔参数32、主副认证1；PPS失败原因已真实追踪。
r87此时处于构建/校验阶段，实机结果以单独runtime报告为准，不能将hardware_verified统一改成true。
旁路实际供电、电流停止/恢复、拔线后电池供电与新内核笔点按/长线/悬浮/休眠仍待验收。
相机/音频/蓝牙和所有原厂ioctl并未完成全量对照，充电class属性完整不等于所有硬件功能通过。
'''
(w/'reports/kernel618-features-repair-r87.md').write_text(new)
partial=w/'reports/kernel618-repair-r86-bypass.json'
if partial.exists():
    r=json.loads(partial.read_text())
    if r.get('original_restored') and any(row['usb']['POWER_SUPPLY_ONLINE']=='0' for row in r['samples']):
        r.update(interrupted_by_user_unplug=True,enable_and_unplug_evidence_captured=True,
                 charging_restore_phase_completed=False,physical_bypass_verified=False,
                 needs_interpretation='On USB power fg currents fell from about -2200 mA each to +17..32 mA; user unplugged before charging_restored phase; original zero restored successfully')
        partial.write_text(json.dumps(r,indent=2)+'\n')
        extra='''

## 旁路部分实机证据（r86，原装充电器）

`kernel618-repair-r86-bypass.json`：属性219从0写1并读回，input_suspend始终0。
开启前fg1/fg2各约-2.2 A（充电），开启后各约+17～32 mA，USB在线、电压约8.7 V。
用户主动拔线后USB online=0，双电池各约+1.1 A供电，系统保持运行；最后恢复开关0已读回。
开启旁路停止充电与拔线供电已有证据；关闭旁路后恢复充电阶段因用户拔线未完成，不能记作完整通过。
'''
        target=w/'reports/kernel618-features-repair-r87.md';target.write_text(target.read_text()+extra)
shutil.copyfile(w/'reports/kernel618-features-repair-r87.md',p/'docs/FEATURES-REPAIR-r87.zh-CN.md')
for name in ['prepare_sheng_repair_r87.py','derive_sheng_repair_r87_tools.py','finalize_sheng_repair_r87_notes.py',
             'test_sheng_pps_auto_r87.py','verify_sheng_repair_r87_btf.py','package_sheng_repair_r87.py',
             'flash_sheng_repair_r87_wireless.py','finish_sheng_repair_r87_wireless.py','check_sheng_repair_r87_nodes.py',
             'probe_sheng_bypass_r87.py','trace_sheng_pps_r87.py']:
    shutil.copyfile(w/'scripts'/name,p/'port-scripts'/name)
print('Saved truthful r86 runtime correction and r87 feature ledger')

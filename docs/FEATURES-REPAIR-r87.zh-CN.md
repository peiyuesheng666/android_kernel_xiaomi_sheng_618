# r87 功能、修复与验证边界

2026-11-11；内核6.18.32，release默认，344模块，基于r76继续修复。

| 功能 | 当前实现与证据 |
| --- | --- |
| 双电池认证 | 原厂属性165，batterysecret真实读写；实机主/副认证为1 |
| 容器支持 | SYSVIPC、IPC/PID/user namespaces、消息队列、devtmpfs、addrtype、IPVLAN/MACVLAN/VXLAN、VLAN/bridge/overlay；内核配置验证通过 |
| IPv6 NAT | built-in IPv6 NAT与MASQUERADE，隔离网络命名空间规则测试通过 |
| SoC/Scene | SoC ID536映射KALAMAP；平台菜单恢复，不代表全部调度策略验收 |
| 正常release行为 | rawdump与300秒fastboot计时默认关闭；正常启动/重启有实机记录 |
| 手写笔 | 原厂充电sysfs与uevent字段，保留32ms滤波；临时关闭时用户报告多次断触，恢复32ms后用户确认不断触 |
| 原厂充电接口 | 补齐57个原厂class节点：旁路1、标量51、特殊5；r87实机全部存在且可读 |
| 旁路供电 | charging_suspend_battery映射固件219，独立于input_suspend42；r87开1保持USB在线且双电池电流近零，关0恢复各约1.6～1.8A充电 |
| 第三方PPS | 实际识别完成立即解锁pd_verifed属性24，不等待1秒；已有1不重写 |
| 原装认证保护 | verify_process非0与非零adapter_id优先原厂；未知/小米SVID且能力≥100W保守跳过，覆盖100→120W原装识别阶段 |
| PPS写0恢复 | batterysecret认证结束写0后即时重判；实机约39ms回1；连续失败最多3次，成功重置预算 |
| PPS兜底监测 | 在线PPS用5秒freezable读取捕捉固件清零；这是监测周期，不是首写等待；断线/非PPS停止周期 |
| BTF构建修复 | 每次重新链接344个.ko，避免旧缓存split BTF；最终ABI与BTF验证通过 |

特殊原厂接口包括batt_sn（属性160，64字节请求/48字节文本）、wireless_tx_uuid
（属性73，44字节请求/24字节文本）、battery_param_reset（原厂固定显示格式100）、
car_app（真实DCIN属性223）和wireless_version_forcit（有界等待、失败传递）。
完整编号、格式与回调哈希见repair-r85.json；未通过写工厂保护参数来做验收。

## 实机证据

现有r87 boot无线刷写并整分区回读一致，Android恢复；本次GitHub整理未再刷写。
华为100W：识别后能力90W、pd_verifed自动1、quick_charge_type4，连续25个采样
保持1；用户确认动画显示90W。batterysecret写0至恢复1实测约39ms。
原装120W路径曾采到ID a819、APDO/power120、fastchg_mode1；长期/反复拔插仍未完成。
r87旁路开→关恢复充电通过；拔电后电池供电在r86相同接口上观察，r87未重复该步。

## 未完成验收及独立配置

90W/120W能力与动画不等于实际输入功率。华为冷却后软件传感器估算输入约49～57W，
3.25A和约18V输入限流可解释该轮约58～59W上限。用户也报告酷态科屏幕四十多瓦。
低SOC峰值没有外部功率计完整验证，当前不提高内核/固件充电电流和保护限制。
身份不明的≥100W第三方PPS仍可能被保守跳过，不能声称覆盖所有第三方源。
手写笔点按重复、悬浮/抬笔、休眠恢复和长期稳定性仍需验收。
相机、音频、蓝牙及全部原厂ioctl没有全量对照，class节点齐全不等于全硬件验收。

本机独立normal温控覆盖曾将前三档33/34/35℃改为34.5/35.5/36.5℃，
37℃后及限流目标保持；服务回读通过，长期效果未验收。覆盖位于/data，
不属于本仓库内核源码、boot或发布源码包；单刷boot不会撤销该配置。
风驰已取消；7.2 zram/swap移植暂停且未应用到r87。

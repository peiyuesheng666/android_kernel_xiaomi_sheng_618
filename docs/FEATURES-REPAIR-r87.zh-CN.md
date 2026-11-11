# r87 功能说明

小米平板6S Pro（sheng），Linux 6.18.32，默认release，内置344模块。

| 功能 | 实现 |
| --- | --- |
| 双电池认证 | 恢复batterysecret使用的真实固件属性165读写 |
| 容器支持 | SYSVIPC、IPC/PID/user namespaces、消息队列、devtmpfs、addrtype与容器网络 |
| 容器网络 | IPVLAN/MACVLAN/VXLAN、VLAN/bridge/overlay filesystem |
| IPv6 NAT | 内置IPv6 NAT与MASQUERADE |
| SoC/Scene | SoC ID536映射KALAMAP |
| release行为 | 默认关闭rawdump与300秒回fastboot计时 |
| 手写笔 | 恢复原厂充电sysfs与uevent字段，保留32ms滤波 |
| 充电节点 | 补齐57个原厂class节点：旁路1、标量51、特殊5 |
| 旁路供电 | charging_suspend_battery使用固件219，独立于input_suspend42 |
| 第三方PPS | 实际识别完成立即自动写pd_verifed=1，无固定首写等待 |
| 原装认证保护 | verify_process非0、非零adapter_id和未知/小米SVID且能力≥100W优先原厂 |
| PPS清零恢复 | 系统写0后即时重判；成功重置失败预算，连续失败最多3次 |
| PPS兜底 | 在线PPS用5秒freezable监测固件清零，断开/非PPS停止周期 |
| BTF构建 | 重链接344个模块，避免复用旧split BTF |

特殊接口包括batt_sn（属性160，64字节请求/48字节文本）、wireless_tx_uuid
（属性73，44字节请求/24字节文本）、battery_param_reset（原厂格式100）、
car_app（真实DCIN属性223）与wireless_version_forcit（有界等待和错误传递）。
完整属性编号、parser、格式和源码回放哈希见provenance/repair-r85.json。

PPS策略不更改电流与温控限制，动画/协议能力不代表实际输入功率；身份不明的
≥100W第三方PPS仍可能被保守跳过。自动功能可通过模块参数sheng_pps_auto_verify禁用。
手写笔长期/休眠恢复、低SOC峰值及全部硬件/充电器覆盖没有完整承诺。

本机独立/data温控配置不在本仓库和发布源码包中；单刷boot不会撤销已有data覆盖。
风驰已取消，7.2 zram/swap移植暂停且未应用到r87。

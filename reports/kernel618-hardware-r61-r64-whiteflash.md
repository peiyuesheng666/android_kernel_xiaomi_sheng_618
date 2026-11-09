# r61–r64 开机白屏定位（2026-11-10）

当前目标只剩开机小米 Logo 白屏。用户已验收手写笔及其他硬件；充电提示音
在原厂内核也有相同行为，用户明确要求停止修复。临时打开的 user 0 secure
`charging_sounds_enabled` 已恢复为 0，不再改动这条路径。

## 固定来源与差异

- 集成源 `JiaqiLi404/android_kernel_618_for_sm8550`：`c3956156ce7c4193c451dfda531fad72d35bfebb`。
- ACK 6.18.32：`ff4a6c3bb0f471a9dd186293a47b62c83829b97d`。
- nuwa 共用 LOS SM8550：`f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d`。
- MiCode sheng：`29db5d592c5b577aa9d9611da988a5e071d100dd`。
- piano 设备参考：`82adb0a5e072aeb90292ad4adff1d92a21580f12`；使用
  `device/xiaomi/piano-kernel` 预编译及头文件，不能据此移植 sheng 面板数值。

LOS 和 MiCode 的 SMMU 在分配 count=0 的匹配条目时也覆盖 SMR 元数据，
并在写 S2CR 时加入 NSH。因此不能声称 NSH 是本移植独有的差异。
6.18 的 `iommu_device_register()` 遍历总线提前探测/附接设备，集成源码已有
`lazy_attach` 兼容开关，可跳过尚无驱动匹配的设备。r64 实测它改变了显示
附接时点，但用户仍确认白屏，尚不能把提前附接认定为根因。

## 时点对照

| 候选 | 唯一人为等待 | 实机结果 |
| --- | --- | --- |
| r61 | DISP CC 注册及运行时交接之后，0.902780–8.930334 秒 | 用户：白闪在长等待之后 |
| r62 | `msm_drm_register()` 入口，3.923943–12.002734 秒；此时还未注册 KTZ、显示 SMMU 和 DSI | 用户：白屏在长等待时，且白屏时间变长 |
| r63 | 所有等待参数为 0；保留固件 SMR 范围 | 用户：仍然白屏 |
| r64 | 所有等待参数为 0；同一 Image，仅 `arm_smmu.lazy_attach=1` | 用户：仍然白屏 |

r62 将故障范围缩到显示驱动入口等待期间已经存在的损坏。固件 splash
`0xb8000000..0xbaafffff`（44 MiB）已作为 non-reusable 内存保留，尚无证据
证明分配器覆盖该区。显示时序读回记录两个固件接口均已启用；这些读数不
等于证明画面正常。

## r63 修正及边界

固件实际条目为 SMR3=`0x80021c00`，S2CR=`3`，SID=`0x1c00`，mask=`2`，
CB3；匹配 `0x1c00`、`0x1c02` 两个 SID。条目 pinned，但 Linux count=0。
旧分配逻辑会将范围缩窄为首次申请的 SID。新逻辑保留 pinned TRANS 条目的
元数据，并在尚无 Linux context 时跳过硬件 SMR/S2CR 重写。

生产函数的旧/新 C 回归用 ASan/UBSan 验证：旧路径丢失第二个 SID；新路径
保留两个 SID，并通过普通映射、配置冲突和回滚检查。旧源快照保留在
`/root/sheng-618/diagnostic/smmu-smr-source-before.c`。

r63 实机证据：

- 1.059157 秒：固件范围及 CB3 回读；1.061068 秒：保留 SCTLR=`e0`。
- 1.071054 秒：首次申请保留 SMR3 id=`1c00` mask=`2`。
- 1.078856 秒：Linux EARLY_MAP context 已分配，但固件 SCTLR 保留。
- 3.951197 秒：splash 映射完成，安装 Linux CB3 SCTLR=`a5f10e7`。
- 3.966031/3.966040 秒：固件 intf2/intf3 timing 均为 enabled。

修正确实生效，但用户验收失败。不能以 SMR 回归通过代替白屏实机验收。
“Linux context 分配后、映射完成前还可能重写 S2CR”仅为待验证假设。

## r64 控制与实机证据

`scripts/repack_sheng618_kernel.py --tag hardware-r64 --base hardware-r63
--smmu-lazy-attach 1` 只修改 cmdline/revision。gzip 解压后的 Image 完全相同，
所有嵌入驱动保持 r63 字节；空 ramdisk、封包回读和 AVB 验证通过。
参数存在性检查读取压缩层的对应源模块，不能在外层 Image 搜索模块字符串。

2026-11-10T07:00:09.7912003+08:00 仅刷入 boot_a 并重启，已核对 product=sheng、
slot=a、unlocked=yes、is-userspace=no。实机 revision=hardware-r64、
lazy_attach=Y、三个等待参数均 0、Android boot_completed=1。

- 1.118601 秒保留固件 CB3。
- 3.993691 秒首次申请保留 SMR3。
- 4.027309/4.044107 秒两个显示设备在 msmdrm_smmu 匹配时才加入组。
- 4.028095 秒推迟 CB3；4.127741 秒安装 Linux context。
- r63 相应显示设备在约 1.071 秒就提前加入组。

用户仍确认白屏。下一步记录 pinned stream 的实际寄存器写入及调用位置，
先证明是否存在映射前的意外改写。

## 哈希和复现文件

| 候选 | boot SHA256 | 此轮模块 SHA256 |
| --- | --- | --- |
| r61 | `d4b84d92bf40619e5d144b1cc898eab1705a8d5cd89bba65f2f9e3efe0b2d9cb` | dispcc `b2f1dc3047e7d99af5e6049a324ac1cec390ac786b9acb2a3d7b24b7c87a7fd3` |
| r62 | `57a40c19880681486af0c756c34d714368b0240d920a6ae3eb0f5b947b12bcb3` | msm_drm `735b0f49aaf44b4b464fd94d506348a6ed74c2c89fc5848a5e3b31f3b9d2d902` |
| r63 | `d54b1110691fa5037f86dcf174922616954669f75ca09830b14354f6d308aa1c` | arm_smmu `8c6f15aee607755b032f1c054e089565c300d4bbfe2f6d16e9b9a5052d398ad1` |
| r64 | `f3eab8427c6b533d90086b7e861a744f52f8b2894fa95a3c477820bdbeeb025a` | 全部同 r63 |

r61–r63 的 344 模块 ABI/依赖、内核导出一致性、gzip、空 ramdisk、封包
回读及 AVB 均通过。保留先前 SMMU handoff/EARLY_MAP 适配脚本及补丁作为
r63 的复现依赖；它们不是本轮新修复的宣称。

原始日志：`reports/device/kernel618-hardware-r61/kernel.txt` 至 r64 同名文件。
原厂模板只读；不擦分区、不备份当前 boot、不内置 KSU/SUSFS、不启用定时
重启或循环刷写，交付最多保留五版。目标仍 active，白屏未修复。

# r67 早期扫描状态追踪（2026-11-10）

r66 的全局 SMMU 属性接管已实机生效，但用户仍确认白屏。本轮只增加
显示时钟和 SMMU 既有 handoff 时点的只读扫描日志，零人为等待。

## 来源及读取范围

固定 piano/nuwa/MiCode/ACK 来源见 r61–r64 报告，已重新核对本地固定 HEAD。
MiCode 显示 DT 来源固定 `0af012cb525b81e293ddc83a5a5c41538946489a`，
`kalama-sde-common.dtsi` 与设备实际导出的
`/root/sheng-618/diagnostic/disklog-r5/live.dts` 均提供：

- mdp_phys、DISP CC 基址及资源大小；代码运行时读取 DT，不硬编码物理基址。
- MDP top 偏移 `0x1000`；DSI intf 偏移 `0x36000`、`0x37000`。
- 10 个 SSPP 偏移；读取 SRC0_ADDR=`0x14` 和 SRC_FORMAT=`0x30`。

集成显示驱动 `sde_hw_intf.c` 定义帧/行计数偏移 `0xac`/`0xb0`、
`sde_hwio.h` 定义 IRQ status=`0x14`、intf status=`0x1c4`。
`INTF_0=1`，DT 的 DSI 槽位 1/2 对应日志 intf2/intf3，欠载 IRQ 掩码是
bit26/bit28。piano 预编译内核不提供本机硬件寄存器替代值。

仅精确 sheng root model 启用读取。所有偏移按 DT 资源大小检查；读取
GDSC=`0x9000`、AHB gate=`0x80a4`、MDP gate=`0x800c`，只在电源开启且
两条时钟未 halt 时触碰扫描寄存器。调用点是原有启动驱动的供电阶段；
无后台定时 MMIO 轮询，无额外时钟/电压投票，不清除 IRQ/status，不读图像
内容，不发面板命令。每次读取后解除映射和 DT 引用。

记录 firmware、after-pll、before-register、registered、clock-runtime-released、
SMMU reset-before/reset-after、context-deferred、mappings-before-install。
用首个状态变化缩小故障区间，不能以帧计数继续增长证明画面正确。

## 构建和刷入

- 344 模块 ABI/依赖通过；仅 arm_smmu.ko、dispcc-kalama.ko 改变，其他二进制保留。
- 内核导出一致性、gzip 解压、空 ramdisk、封包回读、AVB 均通过。
- boot SHA256：`56e49229a88b338a21823962ebff84b6a1ffbdaa1dc10922f34e0757041cfecf`。
- arm_smmu SHA256：`908932d91de46f0d7835b5d26fcffecb1e7b24f29ee845739152c8d51ca890d2`。
- dispcc SHA256：`847947b15d169007cdace9c1e3acc921e813bd3089a8078c217483c91c0b9f98`。
- 2026-11-10T07:16:23.7747555+08:00 仅刷 boot_a 并重启，四项 Fastboot 身份检查通过。
- 原厂模板只读；不擦分区、不备份当前 boot、不内置 root、不启用定时重启或循环刷写。
- 保留 r63–r67 共五版。

## 实机结果

revision=hardware-r67、三个等待参数均 0、Android boot_completed=1，有线
ADB 正常。用户确认仍然白屏。

| 阶段（秒） | 两路帧计数 | IRQ 欠载掩码 | intf status |
| --- | --- | --- | --- |
| firmware，0.891083 | 406 | 0 | `a00` |
| clock-runtime-released，0.903832 | 408 | 0 | `a00` |
| reset-before，1.086992 | 430 | 0 | `a00` |
| reset-after，1.088548 | 430 | 0 | `a00` |
| context-deferred，1.098722 | 431 | 0 | `a00` |
| mappings-before-install，4.058900 | 786 | `14000000` | `e00` |
| consumers-bound，4.075120 | 788 | 0（显示驱动已处理状态） | 0 |

所有记录时点电源=`f822f800`、AHB/core gate=1；两条 VIG 的图像地址
均为 `b8000000`，format=`237ff`。帧计数持续增长，地址没有被替换，
但 1.0987–4.0589 秒之间两路扫描均出现欠载。不能据此证明 SRAM/总线
内容正确，也不能单凭最后状态清零证明白屏恢复。

下一版仅启用最多 3000 ms 的只读观察：每约 10 ms 检查一次，首次欠载、
电源/时钟访问结束或期限到达后停止。无启动停顿，用首次事件与驱动日志
定位相关初始化；该观察默认关闭。原始日志：
`reports/device/kernel618-hardware-r67/kernel.txt`。

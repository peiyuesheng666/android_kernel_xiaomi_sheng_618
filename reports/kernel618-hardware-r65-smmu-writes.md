# r65 固件显示流寄存器追踪（2026-11-10）

只在 r63 的 arm_smmu 模块增加 pinned stream 状态回读及真实寄存器写入日志，
保留原写入值和调用顺序；无等待。此前 r64 的 lazy_attach 对照未修复白屏，
本轮回到默认 N，以追踪 r63 的实际行为。

固定 piano/nuwa/MiCode/ACK/集成来源见 `kernel618-hardware-r61-r64-whiteflash.md`。
本轮复查 LOS/MiCode 的 S2CR 及全局 SHCFG 都使用 NSH；不能宣称该写法仅存在
于 6.18。piano 使用预编译内核，不能提供本机固件运行状态。

## 实机证据

| 时点（秒） | SMR3 / S2CR / CB3 SCTLR | 全局 CR0 |
| --- | --- | --- |
| 1.097434，reset-before | `80021c00 / 3 / e0` | `290406` |
| 1.098673，reset-after | 同固件值 | `e90406` |
| 1.121449，context-deferred | 同固件值；Linux RAM SCTLR=`a5f10e6` | `e90406` |
| 4.062635，mappings-before-install | 同固件值 | `e90406` |
| 4.062702，mappings-after-install | SMR/S2CR 保留；硬件 SCTLR=`a5f00e7`，CBAR=`1f300` | `e90406` |

唯一记录的 CB3 写入来自 `arm_smmu_enable_s1_translation`，在 4.062646 秒将
固件 context 安装为 Linux context。不存在映射准备前的 SMR/S2CR 再次写入
记录，关键时点回读也保持原值。因此撤回“分配 context 后又重写 S2CR”这条
尚无证据的猜测。

reset 唯一变化为 CR0 的 `0xc00000`，即 bypass SHCFG。r66 将只在精确 sheng
model 且 pinned firmware bypass 仍活跃时保留 SHCFG，所有对应 Linux
context 的硬件 SCTLR.M 生效后再恢复标准 NSH。仍需实机验证因果关系。

用户明确确认 r65 仍然白屏；当前问题未修复。

## 构建和刷入

- 344 模块 ABI/依赖通过；相对 r63 仅 arm_smmu.ko 字节改变，其余二进制保留。
- 内核导出一致、gzip 解压、空 ramdisk、封包回读、AVB 验证通过。
- boot SHA256：`39ca48dd2b03617ff166d1e9d8752306b8ff753c5467217e6cde37c7dee11134`。
- arm_smmu SHA256：`e13faad09bbef1bd1438b5c872ad33aaab95b17a17a892017d9b9906dc878041`。
- 2026-11-10T07:03:28.3415719+08:00 仅刷 boot_a 并重启，四项 Fastboot 身份检查通过。
- 实机 revision=hardware-r65，lazy_attach=N，Android boot_completed=1，有线 ADB 恢复。
- 原始日志：`reports/device/kernel618-hardware-r65/kernel.txt`。

原厂模板只读；不擦分区、不备份当前 boot、不内置 root、不启用定时重启或
循环刷写。交付 r61–r65 共五版。只继续修复开机白屏。

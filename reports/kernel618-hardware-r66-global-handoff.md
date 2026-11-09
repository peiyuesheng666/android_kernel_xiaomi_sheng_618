# r66 全局 bypass 属性接管对照（2026-11-10）

r65 实机记录 SMR3、S2CR、CB3 在 splash 映射完成前均保留固件值，但
SMMU reset 将全局 CR0 的 SHCFG 从 0 改成 NSH：`290406 -> e90406`。
r66 只推迟这项全局属性切换，其他 reset 位及寄存器写入沿用原逻辑。

固定来源和差异见 `kernel618-hardware-r61-r64-whiteflash.md`；LOS/MiCode
也使用 NSH，因此这里测试的是保留固件 bypass 的接管时点，不宣称该设置
是集成源独有错误。piano 预编译内核不能提供 sheng 固件寄存器依据。

仅精确 root model `Qualcomm Technologies, Inc. 8550 sheng` 启用新策略。
只要任何 pinned TRANS context 尚未分配，或者 Linux RAM/硬件 SCTLR.M
尚未生效，就保留固件 SHCFG。所有 pinned context 均已启用映射之后，
再设置标准 NSH。先完成 context 写入并执行屏障，再读取硬件判断；避免
仅以 RAM 中 M=1 判定另一 context 的硬件已经接管。

## 检查

- 生产 helper ASan/UBSan 回归：独立 SMR/CB 索引、未分配 context、已分配
  但 M=0、RAM M=1 而硬件 M=0、多 pinned context、bypass/fault、越界均通过。
- 生产旧/新 SMR 分配回归仍通过；普通映射和错误回滚保持。
- 344 模块 ABI/依赖通过；相对 r65 仅 arm_smmu.ko 改变，其余二进制保留。
- 内核导出一致性、gzip 解压、空 ramdisk、封包回读、AVB 均通过。
- boot SHA256：`5b87da24c67a5cbfc27a026ce35d28c89275258a770e34725a49305177af689a`。
- arm_smmu SHA256：`5fbc7703d83de76ab9d8285bfeae2bde8b055a6ec23e87f547b4abba9e63778d`。
- 2026-11-10T07:09:06.8659842+08:00 仅刷 boot_a 并重启；四项 Fastboot 身份检查通过。

## 实机结果

revision=hardware-r66、lazy_attach=N、三个等待参数均 0、Android
boot_completed=1，有线 ADB 正常。用户确认：依旧白屏，本轮未修复。

- 1.122955 秒 reset-before CR0=`290406`。
- 1.124248 秒 reset-after 仍为 `290406`，SMR/S2CR/CB3 保留固件值。
- 1.136895 秒 context-deferred，CR0 仍保留。
- 3.978388 秒映射安装前 CR0 仍为 `290406`。
- 3.978432 秒安装 Linux context 后，3.978446 秒才切换 CR0 到 `e90406`。

因此策略实机生效，但全局 SHCFG 提前切换不能解释全部白屏。接下来记录
显示驱动入口之前的扫描状态，核查供电/时钟接管及其他 SoC 驱动影响。
原始日志：`reports/device/kernel618-hardware-r66/kernel.txt`。

原厂模板只读；零人为等待、不擦分区、不备份当前 boot、不内置 KSU/SUSFS，
不启用定时重启或循环刷写。交付 r62–r66 共五版。当前只修复白屏。

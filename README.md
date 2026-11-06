# Xiaomi Pad 6S Pro: LineageOS bring-up

当前目标：为 sheng 编写独立设备配置，使用 LineageOS 官方 SM8550 5.15 内核，
移植 LineageOS 24.0 / Android 17。类原生系统完成后再开展 6.12 驱动迁移。
piano 仅作组织方式参考，硬件配置以 sheng 原厂固件核对结果为准。

## 工作记录与 Git 提交规则

从 2026-11-06 起，每次完成一项修改、调试或文档工作后，都要更新相关记录并创建一个 Git commit，完成提交后再向用户汇报。

- 在本 README 或对应的 `reports/` 文档中记录本次改动、验证结果以及仍未完成的事项；README 保留最新状态或报告链接。
- 设备树、脚本或补丁如在 WSL 中修改，先将本次实际改动同步回本工作区并核对一致，再提交。
- Git 仓库根目录为本工作区，统一跟踪 `device/xiaomi/sheng`、自编脚本、补丁、清单和整理后的报告。
- 每个 commit 对应一项完成的工作，提交说明写清改动目的；仅提交本次相关文件。已有未提交修改先核对归属。
- 镜像、下载的工具、运行库、原始实机/串口日志和缓存保留在本地，不加入 Git；报告记录其路径和必要的校验值。
- 提交前检查暂存差异并执行与改动相符的验证；汇报时给出 commit 短哈希和验证结果。未通过实机验证的内容明确标注为待验证。
- 初次提交保存当前源码及记录的基线，不根据报告虚构或补造过去的 commit。以后每项完成的工作独立提交。

2026-11-06：建立上述记录与提交规则，并将当前设备树、脚本、补丁和报告纳入初始基线。
当前实机状态见 `reports/SYSTEM_BOOT_STATUS.md`，音频结果见 `reports/AUDIO_OFFLOAD_STATUS.md`。
本次验证：README 与忽略规则的暂存空白检查通过，WSL 设备树 README 与本地逐字节一致，
确认镜像、下载工具和原始实机/串口日志未纳入暂存。历史源码和补丁的既有空白保持原样；本次没有重新构建或开展实机测试。

## 当前约束

- 当前已授权同步和构建完整 LineageOS，源码和输出位于 C 盘承载的 WSL
  `/root/sheng-lineage/lineage-24.0`，不在 E 盘机械硬盘构建。
- 已有 ACK 基线及其工具链位于 WSL `/root/sheng-612`。
- 本目录保存自主编写的脚本、来源记录、分析报告和最终交付物。
- 当前内核使用 LineageOS 官方 SM8550 仓库；piano 和社区 sheng 项目只作阅读参考。
- `Image` 编译通过不等于 sheng 已能启动。跨 5.15 到 6.12 必须处理驱动、
  模块、设备树、启动镜像及用户空间接口的配套关系。
- 原始线刷包目录严格只读，提取和修改全部在外部工作目录完成。
- 不自动执行刷机或分区擦除命令。

## 固件输入

`E:/6/玩机资源/XiaomiPad6SPro12.4刷机资源/sheng_images_OS3.0.303.0.WNXCNXM_16.0/`

来源和构建结果记录在 `reports/`，WSL 工作日志位于
`/root/sheng-612/logs/`。

## 当前 LineageOS 同步

```bash
bash scripts/prepare_and_sync_rom.sh
```

构建工作目录 `/root/sheng-lineage`，日志在其 `logs/` 下。
运行时增加 48 + 20 GiB swap，加上 WSL 默认 12 GiB，合计约 80 GiB。
用户最新设置是全线程（当前24路），开启压缩 ccache，限制10 GiB。
配置保存在 `scripts/rom_build_settings.sh`。
源码同步、设备配置、完整编译以及实机启动是不同的完成状态；
未通过完整编译和实机测试前，不将产物标为可正常开机。

已准备的设备树在 `device/xiaomi/sheng`，按用户要求改为独立配置。
BoardConfig、产品设置、init/fstab、模块清单、属性、overlay、VINTF和SELinux均在本树维护，
不继承其他小米设备树，也不导入公共设备vendor。专有文件统一生成到
`vendor/xiaomi/sheng`，来自只读原厂包的C盘提取物；没有复制piano设备树。
所需通用高通初始化/策略来源保留许可证与迁移记录。
`reports/lineage-preflight.json` 记录编译前检查状态。

完整 ROM 已于 2026-11-05 编译并导出到本工作区 `artifacts/`，整包实机运行尚未验证。
当前没有同步或整包构建进程，旧自动化已删除。`device-audit.pending` 保留，
设备改动后的旧验证记录不可用于直接重编整包。

## 2026-11-06 Recovery 实机进展

- r11 已实际刷入 `recovery_a`，ADB 实机读取确认内核为 `5.15.220-gf9ca2b71f672`；完整 Lineage ZIP 运行仍待验证。
- r7 使用原厂内核隔离显示问题；QTI 显示后端已实测菜单正常。
- r7 内存加载原厂 `touch_report_debug`、两份依赖库及模型后，用户确认点击正常。
- `/dev/block/by-name/misc` 实际存在；补 UFS `bootdevice` 别名后只读打开通过。
  源 fstab 已统一采用 `/dev/block/by-name/`，Recovery 保留兼容别名。
- r8/r9 的内嵌源码内核校验通过，但临时启动尚未确认执行新镜像；后续串口仍显示
  原厂 5.15.178 和旧诊断 init 的 sysfs 交接错误，不能把此日志归到源码内核。
  物理重新进入 Fastboot 后 r10 临时启动成功，用户确认菜单亮屏、misc 错误消失。
- r11 修正原生 init 的硬件 RC 导入位置，ADB 和触摸服务已在实机自动启动。
  实际全屏轨迹确认触摸坐标需旋转 90°；应用后用户确认点击位置与返回箭头正常。
- r12 已刷入 `recovery_a`，重启后 `ROTATION_RIGHT` 自动生效，源码内核、ADB、misc 均验证。
- r13 已将 Recovery 中触摸驱动的固件等待从 14 秒缩为 1 秒，实机固件就绪时间
  从约 18 秒降到 4.86 秒。用户确认响应很快、点击位置正常，全部修改与校验已归档。
  详见 `reports/RECOVERY_STATUS.md`；整包 LineageOS 运行仍待实机测试。
- 新镜像保留原厂 DTB/DTBO/板级模块，仅将内核和 zram/zsmalloc 换为本项目源码构建。
  336 模块的 17045 项导入 CRC、依赖、AVB 和解包回读均通过；这些检查不取代硬件验证。
- 最新详细记录见 `reports/build-and-space-20261105.md` 及各镜像的构建/实机报告。

## 已完成的 ACK 基线构建

在此目录打开 WSL 后执行：

```bash
python3 scripts/probe_sources.py
bash scripts/fetch_ack.sh
python3 scripts/fetch_toolchains.py
bash scripts/build_ack.sh
python3 scripts/export_baseline.py
```

脚本只获取 ACK 及指定版本的 Google 官方编译工具子目录。核心源码位于
`/root/sheng-612/src/common`，初次已获取的源码不会在再次运行时自动更新。
`reports/source-probe.json` 和 `reports/toolchains.json` 记录来源。

当前基线采用 ACK 的 `gki_defconfig`，保留默认的 Rust、BTF、LTO_NONE，以直接 Kbuild 构建
ARM64 `Image`、`Image.gz` 和通用 GKI 模块。它不是 Google 认证的 GKI
发行包，也不是已经适配完成的 sheng 刷机包。

构建状态：`/root/sheng-612/logs/build-status.txt`。
完整日志：`/root/sheng-612/logs/build-ack.log`。
构建产物：`/root/sheng-612/out/ack-dist`。
成功后，`reports/build-result.json` 会记录版本、源码提交、产物哈希和模块验证结果。

导出的开发基线包位于本目录 `artifacts/`，内含内核、配套 GKI 模块及来源记录。
它不含 sheng 的 6.12 厂商驱动，也不含可直接刷入的 `boot.img`。

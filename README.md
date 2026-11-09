# Xiaomi Pad 6S Pro: LineageOS bring-up

当前主系统工程为 sheng 独立设备配置和 LineageOS 24.0 / Android 17，使用
LineageOS 官方 SM8550 5.15 内核。2026-11-08 新增独立的 6.18 移植调查，
驱动以 LOS 官方 SM8550 三仓库为主；2026-11-08 用户允许为缺失平板驱动补用
小米官方 sheng 源码。6.18 最新范围改为仅支持原厂澎湃 HyperOS，取消此任务的类原生适配。
能经绑定和接口核对由 6.18 现有驱动替代的组件直接复用。6.12 保留作开发对照。
piano、LineageOS nuwa 及其依赖仓库作为逐项修复的实现参考；硬件参数和
固件仍须核对 sheng 本机，不能照搬其他型号的值。

6.18 来源、模块兼容性检查与未完成事项见 [reports/KERNEL618_STATUS.md](reports/KERNEL618_STATUS.md)。
触摸、笔、扬声器的最新实机排查见 [reports/KERNEL618_PERIPHERALS_STATUS.md](reports/KERNEL618_PERIPHERALS_STATUS.md)。

2026-11-09 r36：按最新要求关闭内置 KSU/SUSFS；核心和最终内嵌 Image 的
配置、符号表核查通过，旧 r35 的已启用 root 配置被校验门槛拒绝。
启动镜像已封装并回读校验，尚未刷入；不处理 KSU 管理器版本，不制作或
启用无线 ADB 5555 模块，待用户明确说可以做模块后再执行。
去掉内置 root 本身不能证明其他 root 方案可用。详见
[r36 root 移除记录](reports/kernel618-root-removal-r36.json)。

r36 同时收尾此前已发现的 EVA 重编配置回归：恢复上游指定的
CONFIG_MSM_ADSPRPC，三个实际 FastRPC 导入恢复，旧 r35 占位版本被拒绝。
344 模块、20975 项导入 CRC 和 18008 项内核导出通过，官方 boot 封包、
AVB 和解包回读通过；交付保留 r32–r36 五版。录像效果尚未实机验证，详见
[EVA 构建记录](reports/kernel618-eva-fastrpc-config-r36.json)。

2026-11-09 下午 r35：16:41:54 仅刷 boot_a；用户确认进入桌面，五分钟有线
ADB 未出现。用户重新开启无线调试后，确认实际 r35；传感器恢复至 54 项，
两次采样有真实加速度、陀螺仪和方向数据，原 FastRPC 会话分配错误消失。
USB 仍未连接、未充电；传感器长期休眠恢复、炸音、录像、开机白闪和速度
尚未验收。用户要求持续修复，原五分钟停止条件不再默认启用。
误建的十分钟 heartbeat 已删除，持续目标仍有效。从 r36 起去掉内置 GKI
root；KSU 版本处理和无线调试模块都暂缓，待用户说可以做模块时再做
开机开启端口 5555 的模块。详见 [r35 实机记录](reports/kernel618-hardware-r35-followup.json)。

2026-11-09 下午：用户重新要求继续修复，有线 ADB 已恢复。定位 r33/r34 的
FastRPC 重编漏带 tp-autoconf.h：普通 DMA 缓冲被恒定 false 的所有权占位函数
误判为安全缓冲，ADSP 安全会话申请返回 EUSERS，监听服务持续失败。
已恢复两处构建参数，并在重编、模块清单和封包阶段检查四个真实厂商接口导入；
已用旧 r34 验证拒绝、早期及重编模块验证接受。r35 候选已构建，344 模块 ABI、
18008 项内核导出和官方 boot 封包回读通过；尚未刷入，实机效果待验证。
交付目录按既有规则保留 r31–r35 五版。
USB 延迟自行恢复、扬声器偶发炸音和录像失败尚未确认根因或修复结果，详见
[FastRPC 来源与实证](reports/kernel618-fastrpc-config-source.json)。

2026-11-09 07:56：按用户最后要求，手动重启后观察三分钟仍无法连接 ADB，
停止本轮设备调试与刷机。无线调试开机恢复助手已构建、安装并获得一次性
ADB 设置授权，重启前设置写入成功；重启后只有 offline 旧连接，mDNS 未发现
新端口，不能确认开机自启动是否生效。USB/充电及其他内核问题仍未修复。
用户先前已允许无线 ADB 可用时继续，因此下述 r34 五分钟有线停止规则仅为
历史记录；本次以最新三分钟指令停止。未构建或刷入 r35。详见
[助手测试记录](reports/sheng-wireless-adb-boot-test.json)。

2026-11-09 r34：恢复 N81A 原厂初始亮度 307，移除 probe 时关背光造成的
长黑屏路径；补回澎湃 USB HAL 所需的 sheng 只读 enable_msflag=0，兼容
原厂中继器 host 调参属性名。用户实测仍白闪后进入小米 Logo，白闪未解决。
SoC/display 重编及全部 344 个配套模块 ABI、20964 项导入 CRC、18008 项内核
导出、归档权限、来源哈希链、官方 boot 封包回读通过。07:37:08+0800 仅刷
boot_a，无自动重启；07:42:09 完成 300.81 秒检测，有线 ADB 全程未出现，
已按用户规则停止后续修复和刷机。截止前经用户新连的无线 ADB 完成日志抓取，
确认系统正常启动；Type-C 无数据/供电角色，电池报告充电电流为零，USB/充电
仍未修复。交付保留 r30–r34 共五版，原厂包只读。USB 枚举、键盘间歇
失效、相机录像卡死、插电音效、卡顿及开机速度仍未验收。详见上述外围报告。

2026-11-09：r33 已完成内核与全部 344 个模块重编，固定版本为
6.18.32-peiyuesheng-sheng-kernel，构建用户 peiyuesheng、主机 MiFans；
编译器横幅保留 Clang/LLD 版本，完整来源另存构建报告。20957 项版本化
导入、18008 项内核导出、归档权限、官方 boot 模板封包与回读核查通过。
USB 候选修正了 EUSB2 PHY 未获取 ref_clk_src 导致频率读为 0 的错误；
键盘候选缓存首次由原厂 ueventd 加载的 MCU RAM 固件，恢复后重建保活。
持续日志保留两分钟后的低频写入和异常抓取；真实 AArch64 QEMU 已验证
137.985 秒异常栈与普通 panic 落盘。这些检查不代替实机稳定性验收。
07:11 已仅刷入 boot_a，无自动重启。初次有线 ADB 检测超时；07:17 已用原有配对
重新发现无线端口，实机确认 r33 且系统完成启动。USB 仍不可用；时钟0告警
已消失，SS PHY 切换父时钟告警仍在。原厂包只读，最多五版。
用户确认拍照可用；相机录像卡死、键盘/触控板间歇失效、USB 间歇失效、
充电音效卡顿、开机白闪后黑屏及运行卡顿仍列为未完成。新增只读性能采样，
按 CPU/GPU 调频、热状态、系统负载和帧数据排查，不直接改变性能参数。
最新记录见 [外围进展](reports/KERNEL618_PERIPHERALS_STATUS.md)。
NFC 审计见 [reports/kernel618-nfc-audit.json](reports/kernel618-nfc-audit.json)：
官方描述为 NFC 标签触发分享，未发现本机应补的主动 NFC 控制器。

2026-11-08 全量迁移继续推进：LOS Kalama 全套时钟/VDD、SCM/QTEE、RPMh、
SMEM/SOCINFO/SMP2P/AOSS、TLMM、NoC/QoS、PMIC、UFS PHY、GLINK/QMI/PDR、
Q6/PAS/SYSMON/MDT、安全内存、I2C/SPI/GPI、CPU 调频、温度采集/阈值和冷却
驱动已编译；新增 PMIC 外围、UFS host 和 ICE/HWKM/TME 加密链后，105 个基线
加 82 个移植模块通过联合符号与 CRC 核查，共 9,529 项版本化导入。
以上是此前独立移植路线的结果，保留供复用。用户现指定直接使用
JiaqiLi404/android_kernel_618_for_sm8550 的通用 SM8550/澎湃集成，
只补 sheng 板级差异，不再重复开发上游已有功能。首轮 Image 内置 337 个模块，
20,544 项模块导入及内置模块前后 18,008 项内核导出一致性检查通过。
用户随后授权以只读官方 boot 为模板封包并刷入测试，不备份当前 boot；
生成版本最多保留五版。首版和 baseline-r2 交付目录已按此规则清理，原始
Image 仍保留在 WSL diagnostic/baseline-r2/verified/kernel。disklog-r5 已实机验证内核直接保存日志：
从 rawdump 读回两份 CRC 有效记录，确认显示驱动在约 12.38 秒发生空指针异常。
display-r6 的封包工具误将模块加载助手改为不可执行，实机 233 个后续模块均未加载。
display-r7 已改用保留权限的 newc 封包，完整归档权限/负载、ABI 和实际内核
执行助手的 QEMU 检查通过。实机成功建立三组时序对应的七项模式表，越过 r5
空指针位置；仍未开机，最新有效日志至 12.516 秒，未抓到新的 Oops。
当前进一步排查显示初始化的 DP PLL 旧绑定和缺失的最后阶段日志。
display-r8 已加入显示 probe 分阶段落盘检查点，编译、337 模块 ABI、归档权限
和官方 boot 解包回读通过。实机六个 CRTC、硬件/VM 初始化、IRQ 和 DRM 状态重置
均已返回；最新快照至 22.397 秒，最后检查点为 mode_config_reset returned。
display-r9 沿用完全相同的 Image，仅用底座已有 k618_cont_splash=0 开关对照
旧画面接管路径；实机确认开关生效，但仍停在同一检查点，最新快照至 22.329 秒。
fault-r10 已补上异常后的跨 CPU 日志写入，QEMU 真正触发 BUG/panic 后读回完整
寄存器和调用栈，正常落盘及错误分区名称/大小拒写也通过。实机已抓到约 22.5 秒
延迟探测线程在 devices_kset_move_last 因设备链表损坏触发 BUG；显示线程当时仍在继续。
跨 CPU 异常落盘实机有效，破坏链表的分配/释放路径尚待定位，仍未正常开机。
slab-r11 复用完全相同的 r10 Image，只开启 kmalloc-2k 分配/释放来源跟踪；
QEMU 已验证来源栈能落盘，实机确认 DP AUX 注册后在 PLL 失败路径直接释放，
未注销的 I2C 设备留下悬空链表；内存随后被 SSPP 复用。正在验证 AUX 生命周期修复。
详见 [reports/KERNEL618_DEBUG_STATUS.md](reports/KERNEL618_DEBUG_STATUS.md)。
以上为 r5–r11 的历史排查；当前启动与外围进展以开头链接的最新记录为准。

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

2026-11-08 用户新增约定：之后每修一个 bug，先查 piano、nuwa 及相关依赖
仓库如何处理该功能，记录固定提交、适用差异和验证结果。优先使用适合本机的
成熟类原生设计，不默认继续修补原厂实现。用户进一步明确：只参考他们的做法，
新增应用和系统接入自行编写，不导入现成 FaceUnlock 应用。随后用户明确允许
采用开源识别引擎；代码、权重和依赖须分别核对许可证，保留声明与来源，以便
后续发布到 GitHub。私有或许可不清楚的识别库与模型不纳入。原厂组件
只在硬件依赖或有明确依据时保留。当前人脸改查自编软件实现，原厂 miface 与受保护 GPU 合成的
r39 缓解候选停止推进；该候选的源码和构建暂存属性已还原，未封包、未刷入。
参考流程及既有公共源码约束见 `device/xiaomi/sheng/docs/SOURCE_POLICY.md`。

2026-11-07：r20 已正常启动，六分区哈希匹配；型号已恢复 24018RPACC，
marketname 独立设置为 Xiaomi Pad 6S Pro 12.4，tablet 标记正常。电池健康度
仍为 93%；r19 画面、普通触摸已获用户确认。用户仍报告应用识别异常，设置显示名称待修，详见
`device/xiaomi/sheng/docs/r20-identity-20261107.md`。
用户确认画面、普通触摸、RGB 调节和夜间光效有效；白平衡默认开启时，
唤醒密码界面不再短暂发黄，夜间光效过渡平滑。详见
`device/xiaomi/sheng/docs/r18-color-functions-20261107.md`。

色彩要求以最新澄清为准：保持“自适应、生动、鲜艳”列表顺序，只交换后两项
实际功能。r18 已通过用户效果验收，生动=原鲜艳功能，鲜艳=原生动功能；
用户选择鲜艳时，系统实际模式 1 的回读通过。
抬起亮屏用户已确认可用并要求不再处理；AON 服务已接入，“屏幕感知”入口
可用，但用户实测注视时仍会熄屏，功能未验收。
环境色自适应继续使用已有“显示屏白平衡”开关，不新增开关。

- 当前已授权同步和构建完整 LineageOS，源码和输出位于 C 盘承载的 WSL
  `/root/sheng-lineage/lineage-24.0`，不在 E 盘机械硬盘构建。
- 已有 ACK 基线及其工具链位于 WSL `/root/sheng-612`。
- 本目录保存自主编写的脚本、来源记录、分析报告和最终交付物。
- 当前内核使用 LineageOS 官方 SM8550 仓库；piano、nuwa 和社区项目先作源码对照，
  经本机适配、来源记录与验证后才可采用其实现，不能导入其他机型的硬件固件。
- `Image` 编译通过不等于 sheng 已能启动。跨 5.15 到 6.12 必须处理驱动、
  模块、设备树、启动镜像及用户空间接口的配套关系。
- 原始线刷包目录严格只读，提取和修改全部在外部工作目录完成。
- 未获用户授权时不执行刷机；本次 6.18 调试已明确授权封包、刷入和测试。
  官方线刷包保持只读，不擦除分区，不备份当前 boot，生成版本最多保留五版。

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

2026-11-08 aux-r12 已实机越过 AUX 悬空 I2C 设备引发的链表 BUG，显示和 GPU 模块加载完成。
原厂 init 停在 post-fs，尚未开机；日志写入正常运行至 120 秒。详见 reports/KERNEL618_DEBUG_STATUS.md。

2026-11-08 auto-r13 已完成仅测试版 180 秒回 Fastboot、异常捕获后复位和电脑端单轮读日志脚本。
同一 Image 的 QEMU 六项检查通过；实机自动化待验证。ADB 连通后的下一版关闭测试模式。

2026-11-08 auto-r13 实机完成 180 秒超时返回 Fastboot、临时 Recovery 自动读日志并回到 Fastboot，
全程无需手动按键；175 秒任务栈证实 init 正在等待事件。Android 尚未启动。

2026-11-08 modules-r14 修复原厂重复加载 5.15 模块时已就绪替代驱动的识别，
同一 Image 的 QEMU 重复/缺失回归通过，实机待验证；原厂系统包不修改。

2026-11-08 modules-r14 实机解除模块就绪等待，已进入 post-fs-data；现在因 fscrypt-provisioning
密钥负载接口返回 EINVAL 被原厂 init 重启，已自动转 Fastboot 并读回日志。尚无候选 ADB。

2026-11-08 crypto-r15 只加入 fscrypt 负载大小/标志诊断，保持原校验，待实机确认旧 ABI 差异。

2026-11-08 crypto-r15 实机确认旧零 reserved 的 100 字节 wrapped 密钥负载被新接口 64 字节限制拒绝。

2026-11-08 wrapped-r16 已补旧 wrapped provisioning ABI；QEMU 实际 add_key/ext4 ioctl 共 14 例通过，
原始/封装密钥隔离和长度检查保留；真实 ICE 派生与启动待实机。

2026-11-08 wrapped-r16 实机通过加密初始化；下一卡点是 Wi-Fi 固件加载兼容。
真实 panic 自动回 Fastboot 并读日志成功，三种测试回退路径均已实机验证，尚无候选 ADB。

2026-11-08 firmware-r17 恢复原厂 5.15 的 firmware SELinux 加载接口，强制模式保持；
新旧 Image 实际固件加载与权限拒绝对照通过，实机待验证。

2026-11-08 firmware-r17 实机在 79.076 秒完成 HyperOS 启动，用户确认进入系统；
花屏与 USB 无可用 UDC 尚待修，ADB 未通，180 秒回 Fastboot 已触发，日志已保留。

2026-11-08 usb-r18 补齐 DT 依赖的 PS5169，测试超时改为十分钟；
338 模块 ABI 与日志回卷身份 QEMU 检查通过，实机 USB/显示待验证。

2026-11-09 usb-r18 已实机连通 6.18 ADB、完成系统启动；后续断连，
十分钟复位触发但未自动返回，触摸/传感器/音频仍待修复。详见实机报告。

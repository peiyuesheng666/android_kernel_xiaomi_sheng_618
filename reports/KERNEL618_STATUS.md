# sheng 6.18 移植：来源和 ABI 核查

2026-11-08 最新用户指令：直接使用 JiaqiLi404/android_kernel_618_for_sm8550
作为主底座，仅补小米平板 6S Pro 的板级差异，保留此前有用的移植成果。
此任务仅支持原厂澎湃 HyperOS，取消类原生目标，不再独立重做上游已有的
澎湃适配。最初交付原始 `Image`；用户随后授权封包、刷入并直接调试。

2026-11-08 实机调试更新：disklog-r5 的内核日志落盘已验证，Recovery
读回两份 CRC 有效快照，最新记录至 13.273 秒。第一处明确异常发生在
12.378560 秒，`msm_drm` 的 `dsi_display_get_default_lms()` 空指针访问。
该证据来自本机 6.18 运行；不能用其他版本 Recovery 日志替代。
封包与 USB 尝试、落盘区域、校验结果和限制见
[KERNEL618_DEBUG_STATUS.md](KERNEL618_DEBUG_STATUS.md)。尚未正常进入系统。
display-r6 的 mkbootfs 封包丢失 /k618_umh 执行权限，导致 233 个后续模块未加载。
display-r7 已保留完整归档权限，337 模块/20,544 项导入与 18,008 项内核导出
检查通过，QEMU 已实际执行内嵌助手加载模块。实机模式表为三组时序、七项模式，
越过 r5 的空指针位置，但仍未开机；最新快照至 12.516 秒，无新的 Oops 栈。
DP PLL 报缺少 qcom,dp-pll，新驱动与原厂旧式内联 PLL 绑定不同；尚未认定其为停机原因。
display-r8 已加入仅用于诊断的 probe 检查点并刷入 boot_a，保留已验证的日志写入器、
模块助手权限和七项模式表；构建/ABI/封包检查通过。实机六个 CRTC、硬件/VM 初始化、
IRQ 和 mode_config_reset 全部返回，快照至 22.397 秒，尚无最终异常栈。
display-r9 只改变已有 k618_cont_splash=0 启动选项，完全复用 r8 Image，
实机确认开关生效，但最后检查点仍为 mode_config_reset returned，快照至 22.329 秒。
fault-r10 继续复用 r8 显示模块，只补强 ARM64 __die 打印后的日志抓取：从其他 CPU
唤起写入，异常 CPU 最多延时 1.5 秒一次。模拟 BUG/panic 的寄存器/栈落盘、
真实块写入和分区拒写检查通过；已刷入 boot_a，实际故障是否进入该路径仍待验证。

首轮测试产物曾导出为 `artifacts/sheng-6.18-first-boot/Image`，
64,506,368 字节（约 61.5 MiB），SHA256 为
`32afc9fa288989a949e8d5c6e83c159110d9ea62e60bd016efde7de7e7c58b70`。
来源为用户指定仓库固定提交 c3956156ce7c4193c451dfda531fad72d35bfebb。
249 个 SoC 模块和 30 组 techpack 构建全部通过（techpack 导出 81 个模块），
此前 CS35L43 和 POGO 公共模块源码已复用并按新底座重编。最终 Image 的模块层
共 337 个模块，采用 sheng 原厂第一/第二阶段清单，并按实际依赖排序；
生成依赖信息时修正宿主 PATH 缺少 /usr/sbin 导致找不到 depmod 的问题。

实际导出文件与 WSL 构建文件及 SHA256SUMS 一致；ARM64 Image 头、内置 cpio、
337 模块依赖覆盖、20,544 项真实版本化导入、module_layout、缺失提供者与重复
导出核查通过；内置模块层前后 18,008 项内核导出及 CRC 完全一致。
结果见 `kernel618-upstream-image.json` 和 `kernel618-upstream-layer.json`；
原首版及 baseline-r2 交付目录已按最多五版的约定清理；同一 Image 仍保留在
WSL /root/sheng-618/diagnostic/baseline-r2/verified/kernel。
原验证脚本固定引用首版目录，后续诊断版须使用各自的构建、解包与 ABI 检查，
不能直接用该脚本把新的 native 输出当作首版。

这是首轮开机测试候选，不能视为全部功能移植完成。NT36532 触控/笔、metis、
Nanosic 键盘、xiaomi_keyboard_driver、hall 等平板来源缺口仍在；充电整链、
LCD/音频/相机等板级行为及加密 userdata 均未实机验证。原首阶段清单有 28 个
名字未同名提供，其中包含已内置/合并/其他 SoC 候选和仍待补齐项，不能将这个
数量当作最终缺失模块数。上述首版检查时尚未执行设备操作；现已测试 boot_a。
未将原厂 5.15 模块混入 Image。

新入口 `python3.11 scripts/prepare_sheng618_upstream.py --only soc` 已重建
原仓库固定提交的 ACK 和 SoC 集成补丁，SoC tree 校验为
`3ddaf72a978d520b5ce6aa5e25d5a21d13f9787f`。源码和后续构建位于
`/root/sheng-618/upstream-build`，脚本位于 `/root/sheng-618/upstream-project`。
早先 clean ACK、LOS/MiCode 输入和 `/root/sheng-618/ports` 保持原状；
后续只在新底座需要时复用平板驱动、修复和构建生成器。
`--only sources` 继续获取上游固定的工具链与 techpack；不获取 nuwa 手机
固件用于平板启动，不执行原仓库的刷机入口。

上游固定的 15 个源码/工具输入和两份 techpack Git 引用现已准备完成，见
`kernel618-upstream-sources.json`。原仓库通用内核编译已通过；配套新版 Rust
默认生成 ZSTD 压缩调试信息，已为本机私有 elfutils 补齐解压支持，安装的
`libzstd-dev` 仅新增开发包，没有升级或移除系统包；早先 elfutils 前缀保留。
`build_sheng618_upstream.py` 依次调用原仓库 kernel / SoC / techpack 构建，
将旧的 POGO、CS35L43 适配源码复制到独立目录重编。最终沿用原仓库模块层
生成和 Image 重链接机制，改用 sheng 的加载清单与 init_boot 输入，只导出
内置模块层的 `Image`。导出前检查真实符号 CRC、缺失提供者和 module_layout；
不会把原有纯 ACK Image 当作已移植产物交付。

重跑（Ubuntu 22.04 已安装 libzstd-dev）：

```bash
python3.11 scripts/prepare_sheng618_upstream.py --only sources
SHENG_ELFUTILS_PREFIX=/root/sheng-618/host-tools/elfutils-0.193-zstd bash scripts/prepare_kernel618_host_tools.sh
python3.11 scripts/build_sheng618_upstream.py all
python3.11 scripts/verify_sheng618_image.py
```

下述是此前独立移植路线的历史结果：105 个 ACK 基线模块加 82 个移植模块通过
编译及联合静态核查；尚无完成板级适配的 sheng 内核、boot 镜像或可刷包。
用户要求能由 6.18 现有实现替代的组件直接复用，不能按原厂 .ko 数机械地逐个重搬。

### 用户要求全量推进后的平台阶段

2026-11-08 UFS 与安全存储批次新增 12 个模块，联合核查 9,529 项版本化导入通过。

- PMIC power-on、REVID、PBS、misc、PM8xxx RTC 和 QFPROM 六个外围模块编译通过。
  更新 class 回调 const 参数与平台 remove 接口，保留原电源/时钟/熄屏控制逻辑。
- 依照官方 sheng_GKI.config 的 HWKM 配置，使用 LOS crypto-qti-common、
  crypto-qti-hwkm、hwkm 和 TME mailbox 接口四模块；保留原 SCM 和共享内存协议。
  密钥字段改接 ACK blk_crypto_key.bytes，去掉原始错误路径输出密钥内容的日志。
  补齐 TME 公共声明和内核类型头，修复寄存器转储中的格式与参数不匹配。
- LOS UFS host/ICE 和 UFS QTI crypto profile 两模块编译通过。ACK UFS 核心继续
  内置复用，不重编第二套核心。核心结构保持 ACK 定义，三条私有供电轨独立保留
  旧有电压字段。查询 ioctl 0x5388 和 compat_ioctl 保留，使用模块静态生命周期
  的 SCSI 模板副本承载回调，不修改只读核心模板。
- 功耗参数协商迁入新 negotiate_pwr_mode，在 TX equalization 前完成；PRE_CHANGE
  仅执行硬件前置动作，避免把降频请求覆盖为设备最高 gear。Toshiba 断电后等待
  使用 ACK vcc_off_delay_us，实际等待由核心 VCC 关闭后执行。保留板级供电参数。
- 加密接入真实 blk_crypto_profile，提供硬件封装密钥 program/evict/derive_sw_secret，
  保留时钟 hold/release 和硬件 capability 检查；错误向上传递。全局 UFS hook 改为
  模块加载时注册一次、失败时回滚、卸载时注销并等待回调，过滤其他 UFS host。
  旧 REQ_HIPRI 的请求内修改改成 REQ_PRIO，避免把已按中断分配的请求变为轮询。
- 新 block import/generate/prepare 操作尚不支持。ACK 与原厂 fscrypt/dm 的封装
  密钥用户空间接口仍需适配核对，不能据此宣称澎湃能解密 userdata。原先历史
  中断时间戳不再可用，诊断明确读取当前中断状态；完整 minidump 和 probe/remove
  故障注入、DTB 绑定、启动和实机存储均待验证。

重跑追加组名：`pmic-peripherals`、`crypto`、`ufs-host`，最后执行联合核查脚本。
参考仍为固定 nuwa 6.18 提交 c3956156ce7c4193c451dfda531fad72d35bfebb；该项目
替换 UFS 核心的做法仅作对照，本批使用真实 ACK 核心导出，未复制手机硬件参数。

2026-11-08 总线与温控批次：在前一批次上新增 16 个模块，现为 105 个基线
加 70 个移植模块；9,024 项版本化导入的联合核查通过。

- LOS I2C/SPI/GPI 三个模块直接使用 ACK 已内置的 GENI 核心，公共结构和真实
  符号 CRC 一致，未引入第二套 wrapper 驱动。更新 SPI controller、target_abort
  和多片选访问接口。I2C remove 先删除 adapter/client 并同步标记 suspended，
  再释放 DMA/时钟，避免新版 void remove 下遇到传输仍直接返回。
  I2C test-bus 诊断显式映射父设备寄存器，修复旧 helper 把 geni_wrapper 的私有
  数据误当 geni_se 访问的问题，保留原诊断寄存器和功能。
- LOS CPUFreq HW 保留 LUT、boost 和 LMH 逻辑，改用 ACK 按频率上限计算的
  HW pressure 接口；退出时清除 pressure。Boost 支持改接当前 per-policy 核心
  流程和 cpufreq_boost_set_sw，频率列表 sysfs 由当前核心提供。
- TSENS、SPMI ADC5、VADC common、ADC TM5、PMIC temp alarm 和 LMH 六模块
  通过。温区回调用 adapter 获取当前 zone 私有数据；trip 索引显式转换为 ACK
  descriptor 中的真实 trip，不假定 trip 数组连续。保留模式切换的阈值重置和
  冷却实例释放，更新为每个 trip 的实例链。IIO 使用 fwnode xlate/channel API。
  完整 thermal minidump 仍未启用，未验证设备树温区绑定及实际温度值。
- CPUFreq、devfreq、userspace、QMI、DDR 和 regulator 冷却六模块通过，保留
  QoS、QMI 和供电控制；未修改硬件限温参数，也未证明整机温控策略完整可用。

重跑组名为 `buses`、`cpufreq`、`thermal`、`cooling`。这些结果只覆盖源码编译与
静态 ABI 闭合，尚无 sheng 启动镜像或硬件验收结果。

2026-11-08 后续批次：PMIC、UFS PHY、IPC 和 remoteproc 共新增 25 个模块，
现为 105 个基线加 54 个移植模块；8,338 项版本化导入的联合检查通过，
无缺失提供者、CRC 差异、重复导出、命名空间或依赖环错误。

- PMIC arbiter、SPMI PMIC、GPIO/MPP、SDAM、PDC、GDSC regulator 和 proxy
  consumer 八个模块保留 LOS 的供电和中断语义。GPIO fwspec 改填内核提供的
  union，set 返回真实 pinconf 结果，GDSC 使用当前 ACK 的 regulator 内部结构。
  QTI regmap 诊断扩展仍未启用。
- UFS 公共 PHY 与 Kalama QMP v4 两个模块编译通过，保留 LOS 的表和绑定。
  UFS host、ICE 及其整链集成尚未完成。
- GLINK/native/SMEM、SSR、memshare、QMI、PDR、PMIC GLINK 和 packet/probe
  共八个模块通过。ACK RPMSG 公共结构不含 LOS 的 rx_done/signals 扩展；
  扩展状态迁入私有通道，保留延迟 intent 释放，按端点 ops 检查调用类型。
  信号回调安装与清除和接收锁同步，移除 packet client 时先清回调。
  vm_flags、IDA、timer API 已更新；修复早期失败路径释放错误 minor 的问题。
  PMIC send 在 size_t 转为 rpmsg int 长度前检查范围和报头长度。
- Q6V5、PAS、SYSMON、PIL info、MDT loader、secure buffer 和 ramdump 七个
  模块通过，使用 ACK 的 remoteproc 公共和内部结构及 LOS Kalama 资源定义。
  两个 SYSMON timeout 保留 LOS Kconfig 默认 10 秒；secure buffer 用 PFN
  换算替代移除的 nth_page，保留跨内存 section 的逐页私有标记。
  崩溃/minidump 可选路径未全部迁移，DSP 固件启动仍未实测。

重跑追加：`python3 scripts/build_kernel618_platform.py pmic`、`ufs-phy`、
`ipc`、`remoteproc`，随后执行 `python3 scripts/verify_kernel618_build.py`。
所有新模块仍为外部编译产物，未安装、未签名、未制作启动镜像。

2026-11-08：继续源码迁移，新增 `build_kernel618_platform.py` 和共享的
`kernel618_portlib.py`。各组独立暂存，输入固定且干净，所有转换先生成再写入，
失败的转换不会覆盖上一次有效暂存；记录源码/生成文件/编译结果与模块哈希。

- `clock-los` 替换先前仅 TCSR 的实验组：公共 LOS 时钟库、dummy clock 及
  GCC/CAMCC/DISPCC/GPUCC/TCSR/VIDEOCC/DEBUGCC 共九个模块通过编译。
  保留 LOS 的 PLL、VDD vote、proxy vote、OPP、PM 和 critical clock 处理；
  适配 OF 属性迭代、trace string、日志和 remove 接口，没有删除电压管理。
- LOS SCM 与 QTEE shared-memory bridge 编译通过，保留安全调用和共享内存路径。
  三个仅文件内使用的函数改 static，删除一个未使用的 ION include。
- LOS RPMh/RSC、command DB、IPC logging、RPMh 时钟和 regulator 共五个模块通过。
  使用 LOS 头文件中的 fast-path 和 clock ID，避免被 ACK 同名头文件覆盖。
  IPC minidump buffer 数取其原 Kconfig 默认值 0，完整 minidump 尚未迁移。
- SMEM、SOCINFO、SMP2P、AOSS、硬件自旋锁及 IPCC 共六个模块通过。
  SOCINFO 保留按版本累加 sysfs 属性的行为，显式标注 fallthrough。
- TLMM core 与 Kalama pinctrl 两个模块通过；GPIO set 返回状态、fwnode、
  valid-mask 查询及 pinconf LEVEL 接口已按 6.18 适配，保留 GPIO/唤醒表。
- Kalama NoC、RPMh ICC、BCM voter、QoS 共四个模块通过。ICC provider 改为
  init → 创建节点/配置 QoS → register，卸载先 deregister；删除 devm clocks
  的重复释放，移除 probe list 项。LOS 的 translator 改为独立符号，避免与 ACK
  已内置的同名导出冲突。没有移除原有带宽投票或 QoS 实现。
- `ports.json` 明确选择有效模块组，并排除被替代的旧 `clock` 组。联合核查
  105 个基线与 29 个移植模块（合计 134 个）、7,218 项版本化导入通过，未发现
  缺失符号、CRC 冲突、重复导出、命名空间或依赖环问题。完整报告已重生成。

这些是编译和静态闭合结果；存储、IOMMU、USB、显示、完整音频、GPU、无线、
充电、触摸/笔/键盘等仍需继续迁移。尚未形成完整可启动的板级模块集合。
新模块尚未安装或签名，无刷机和硬件验证。

## 选定来源

2026-11-08 用户最新确认：SM8550 驱动以 LOS 官方三仓库为主，缺失的平板驱动
允许补用小米官方 sheng 源码。LOS 版本与当前 ROM 已审计的输入一致；没有改动现用
ROM 的公共源码、BoardConfig、模块选择或任何设备分区。

| 仓库 | 固定提交 |
| --- | --- |
| [LOS kernel](https://github.com/LineageOS/android_kernel_xiaomi_sm8550) | `f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d` |
| [LOS modules](https://github.com/LineageOS/android_kernel_xiaomi_sm8550-modules) | `92a9fde479d3262da080cfd28bab0775b0da500a` |
| [LOS devicetrees](https://github.com/LineageOS/android_kernel_xiaomi_sm8550-devicetrees) | `43b5ada5654ed84c25f74789bc8f6326b7bacd20` |

LOS 内核输入仍是 5.15。6.18 核心参考 ACK
`ff4a6c3bb0f471a9dd186293a47b62c83829b97d` / 6.18.32；需要将 LOS 的相关驱动和
接口迁移到该核心，不能通过修改 Makefile 版本号得到 6.18。

[13 Pro 参考项目](https://github.com/JiaqiLi404/android_kernel_618_for_sm8550)
固定在 `c3956156ce7c4193c451dfda531fad72d35bfebb`。它用于研究移植与打包方法；
不能直接使用 nuwa 的启动镜像、手机触摸配置或面板参数。参考项目自己的 README
仍标注真机验证待完成。

本项目的输入选择在
`device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json`。
三个 LOS 仓库已经完整检出在 `/root/sheng-618/src/lineage-*`。官方 sheng 补充
来源固定在同一 source-plan 的 `supplemental_board_sources`，内核、音频和两份
设备树、显示和相机驱动均已完整检出。固定提交、树 ID、实际检出
状态和文件名覆盖见 `kernel618-source-audit.json`。

## 2026-11-08 实际构建与平台、板级模块移植

- ACK 核心保持固定提交且工作区干净；24 线程编译成功，版本为
  `6.18.32-4k-android17-5-sheng-ack-baseline`。输出在
  `/root/sheng-618/out/ack-dist`，包括 Image、Image.gz 和 105 个配套 GKI 模块。
- Ubuntu 的 elfutils 0.186 无法解析 Clang 生成的 Rust helper DWARF5 行表；
  仅禁用 ZSTD 压缩也不能解决。新增私有 elfutils 0.193 准备脚本，固定归档 SHA256，
  不替换系统库；确认 gendwarfksyms 实际加载私有 libdw/libelf。保留 Rust、BTF、
  MODVERSIONS 和 GENDWARFKSYMS。
- 实际复用 ROM 的 Clang r584948b 和 Rust 1.91.1，与 ACK 推荐的 r584948c /
  1.91.1.p3 不同。记录实际版本和哈希，不宣称兼容 madrid 二进制或其 KMI。
- 从固定 LOS 内核移植 `tcsrcc-kalama.c`，保留六路时钟的编号、寄存器和
  `qcom,kalama-tcsrcc` 绑定。使用未修改的 ACK 公共时钟代码生成 clk-qcom.ko，
  单独生成 tcsrcc-kalama.ko；输入源码不修改，每个暂存文件记录来源及哈希。
- TCSR 没有 voltage proxy votes 或 critical clocks，sync_state 改接 ACK 的
  clk_sync_state；保留休眠恢复的 clk_restore_context。ACK 无下游 DEEPSLEEP
  扩展，此路径未实现、未实测，其他控制器的 PLL/电压框架仍待迁移。
- 从官方 sheng 内核移植 xm_utils.ko，包括 battmngr 的 notifier、voter 和设备类；
  更新 class_create 接口并将模块初始化/退出函数限制到文件内，没有改变充电参数。
  完整 charger、virtual_fg、nanosic_platform 和 PMIC GLINK 尚未移植，不能宣称充电可用。
- 从官方 sheng 音频仓库移植 cs35l43_dlkm.ko，保留 I2C 绑定和异步固件加载，
  更新 I2C probe/remove、ASoC DAI/压缩音频回调、64 位时间戳及错误日志的指针/
  size_t 格式。保留原固件与寄存器逻辑。
  ONETRACK/MIEV 遥测暂未启用，其 mihw 提供者未迁移。功放模块编译通过不代表
  Qualcomm 音频平台、声卡、路由、DSP IPC 或六扬声器已可用。
- ARM64 Image 头、gzip 回解、分发副本哈希、109 个模块的结构和依赖闭合、
  6,330 项真实导入 CRC、命名空间和依赖排序检查通过，无缺失符号或重复导出。
  基线模块有签名尾部；未做签名密码学验证，四个新移植模块尚未安装或签名。
  完整验证、每个实际输入文件/暂存文件的哈希和产物哈希见
  `kernel618-build-verification.json`。基线/TCSR 提交为 `0314a96`；没有刷机或修改原厂固件。

## “只换内核、不动模块”的核查

参考项目依赖 `.ko`，并声明统一生成 406 个配套模块：公开驱动重新编译，另外
选用 madrid 官方固件中的 54 个 6.18 模块。它修改 initramfs 解包顺序，把自带的
模块层解包到 bootloader 提交的启动盘之后，覆盖同名模块和加载清单；原有
init/vendor/recovery 启动逻辑仍负责启动。只刷 boot 是交付方式，不能推出运行时
完全沿用原来的 5.15 模块。源码证据的具体行号和哈希见 `kernel618-source-audit.json`。

因此，6.18 适配可研究“只交付一个 boot，但内含匹配的替换模块层”的方式。
是否适用于 sheng 的 init、vendor_dlkm 和 system_dlkm 加载路径，仍需另行验证。
本次没有制作这样的包，也没有绕过 CRC 检查或修改原厂模块。

## 实际模块核查

新增 `scripts/audit_kernel618_modules.py`，逐一验证原厂 BSP 清单中的 417 个模块
SHA256。候选核查另加入候选内核编译的 zram/zsmalloc，合计 419 个有效模块。
检查 basic/extended modversions、真正的符号提供者、重复导出、缺失符号、
`module_layout`、vermagic 标志和 `.gnu.linkonce.this_module` 大小。

| 对照 | 结果 |
| --- | --- |
| 当前 LOS `5.15.220-gf9ca2b71f672` | 25,134 项版本化导入全部匹配；无缺失符号、CRC 或结构大小错误 |
| 已有 ACK `6.12.96-4k-android16-7-sheng-ack-baseline` | 检查 25,216 项；19,002 项 CRC 不同、2,990 项缺失提供者、52 项重复导出；417 个原厂模块结构均为 960 字节，候选模块结构为 1,600 字节 |
| 新 ACK `6.18.32-4k-android17-5-sheng-ack-baseline` | 25,215 项导入；18,636 项 CRC 不同、3,356 项缺失提供者、52 项重复导出；417 个原厂模块结构均不匹配，不能混用 |

5.15 对照还发现三个已解析、但原厂未提供 CRC 的导入（btpower 两项、nxp-nci
一项）。真实加载器允许这些导入；报告列为 warning，不把它们写成“已由 CRC
证明兼容”。静态核查不替代签名、命名空间、设备树绑定、内存语义或硬件测试。

6.12 是用于检验核查工具能拒绝跨版本不匹配输入的真实对照，不是 6.18
的实测结果。6.18 的真实结果单列于 `kernel618-audit-candidate-618.json`；它核查
“基线加原厂模块”的不兼容性，不等同于上面 109 个新编译模块的闭合检查。

结果分别见 `kernel618-stock-inventory.json`、`kernel618-audit-control-515.json`
和 `kernel618-audit-control-612.json`。失败报告保留准确总计和前 80 条示例，
避免将完整重复错误列表纳入 Git。

核查工具还通过五项验证：真实 5.15 模块对照、禁止 5.15 候选冒充 6.18、
删除临时 symvers 副本中的 module_layout 提供者后拒绝全部 419 个模块、
长符号名 extended modversions 解析、截断 CRC 数组拒绝。
结果见 `kernel618-audit-tool-validation.json`；临时副本检查没有修改真实内核
输出或原厂模块。

## 仍需解决的适配

三份固定 LOS 仓库的文件目录检索未找到平板特定的 NT36532、Nanosic 键盘、
霍尔、metis、POGO 充电、CS35L43 和 N81A 面板实现文件。补充官方 sheng 来源后，
已找到 POGO、CS35L43 和面板来源，九仓库的文件名检索仍缺少 NT36532、
Nanosic 键盘、霍尔和 metis。这不代表全网没有公开实现；命中一个 touchfeature
文件也不能证明它兼容平板
的 host-processing/笔协议。当前可用 5.15 方案依赖原厂 BSP 模块，不能据此宣称
LOS 公共源码已经完整重建平板驱动。

下一阶段必须处理 LOS 通用驱动到 6.18 的迁移和这些平板接口，再完成有效模块
闭合、合并 DTB/DTBO 绑定、启动包及 AVB 检查，最后在授权后做实机启动和硬件验证。

C 盘约剩 10.3 GiB。容量工具验证当前注册 VHDX 非 sparse/压缩文件，并计算已
分配块内可复用空间的保守下界；构建前有效预算约 83.8 GiB，包含约 73.5 GiB
已落盘的可复用空间，故 40 GiB 预留检查通过。不能把 WSL 内部约 505 GiB 空闲
全部当成宿主容量。没有清理其他任务的产物或缓存。容量读数见
`kernel618-wsl-space.json`。

## 重跑

```bash
# 获取/复用固定的 LOS Git 目录索引，无完整检出、无编译、无刷机。
python3 scripts/prepare_kernel618_sources.py --catalog-only
python3 scripts/audit_kernel618_sources.py --output reports/kernel618-source-audit.json

# 检查完整构建的预留空间；空间不足返回 2。
python3 scripts/prepare_kernel618_sources.py --preflight

# 编译基线、首个 LOS 控制器，再验证真实产物。没有刷机操作。
bash scripts/build_kernel618_baseline.sh
bash scripts/build_kernel618_clock_port.sh
bash scripts/build_kernel618_pogo_port.sh
python3 scripts/build_kernel618_cs35l43.py
python3 scripts/build_kernel618_platform.py clocks
python3 scripts/build_kernel618_platform.py firmware
python3 scripts/build_kernel618_platform.py rpmh
python3 scripts/build_kernel618_platform.py soc
python3 scripts/build_kernel618_platform.py pinctrl
python3 scripts/build_kernel618_platform.py interconnect
python3 scripts/verify_kernel618_build.py

# 检查原厂 BSP 原始文件哈希和 ELF 信息；成功只是清单核查成功。
python3 scripts/audit_kernel618_modules.py \
  --stock-root /root/sheng-lineage/firmware-dump/hardware/modules \
  --output reports/kernel618-stock-inventory.json
```

候选检查时再提供 `--kernel-out`、两个 `--gki-module`，默认要求 6.18。
现有 5.15/6.12 对照必须明确设置 `--expect-series`，不会冒充 6.18 结果。


### fault-r10 实机结果：取得真实终止异常

用户反馈仍失败并返回 Fastboot。临时启动已验证的 r13 Recovery，仅读取 rawdump
288..290 MiB；两份 CRC/尾标记有效，run 0e81e82e6a32bec4，seq68/69 分别至
22.365/23.278 秒，实际 cmdline 为 sheng_test=fault-r10。
22.511149 秒 devices kset 链表 prev->next 为 NULL，lib/list_debug.c:34 触发 BUG。
CPU6/PID222 为 events_unbound deferred_probe_work_func，调用链为
device_pm_move_to_tail → device_reorder_to_tail → devices_kset_move_last →
__list_add_valid_or_report。损坏 entry 位于 kmalloc-2k 对象偏移 480。
最新快照保存了 PC、寄存器、完整调用栈及跨 CPU 抓取窗口标记，异常落盘实机通过。
显示线程 PID611 在异常期间仍记录了 23.229868 秒 cont_splash_config begin，
因此前几轮的最后显示检查点不能作为实际终止位置。
目前只证明设备链表损坏，尚不能确定哪个驱动写坏或释放了对象；不删除链表校验，
不将 DP/HFI 错误当作此异常的已证根因。下一步追踪 kset 对象和 slab 分配/释放来源。
原始日志 reports/device/kernel618-fault-r10/，整理见 kernel618-fault-r10-hardware.json。


### slab-r11：实机取得 DP AUX 提前释放来源

复用 fault-r10 的相同 Image 和全部模块，不重新编译。仅 boot cmdline 新增
stack_depot_disable=off slab_debug=U,kmalloc-2k，用 ACK 原生 SLAB_STORE_USER
在 list_debug 的既有 kmem_dump_obj 输出中显示分配/释放栈。
只跟踪 r10 已确认的 kmalloc-2k 池，不更改设备链表校验或绕过 BUG。
依据固定 ACK ff4a6c3bb0f471a9dd186293a47b62c83829b97d 的 mm/slub.c、
lib/stackdepot.c、mm/slab_common.c；原厂早期 stack_depot_disable=on 由后续 off 覆盖。
这会改变该池的对象布局和时序，抓到分配者仍不一定等于证明了破坏者。

QEMU 用交付 Image 和仅测试 initrd 的临时模块分配/释放 1900 字节对象并 BUG，
实际读回两份 CRC 有效快照至 12.471/13.410 秒，包含 allocation/free 栈及异常栈；
命令行 on→off 覆盖实测生效，真实内嵌助手执行成功。首次验证的断言误用了
静态函数名 fault_init，而模块符号实际为 init_module；修正断言后重跑通过。
故障模块不在交付 Image 中。未重复与此次参数无关、r10 已通过的分区拒写测试。
官方 boot 只读封包、AVB 自校验、解包 kernel/空 ramdisk 回读通过。

boot SHA256: 478233b98b5af557fd4a1c0bbc0206e12fb7ed05dfbe2c76fe4452767722914c。
Image SHA256: 99d34cdb44cf1174c23451aad863adbc459d728268c509ca4905c632285e8f6a。
Recovery ADB 重启到 Fastboot，核对 sheng/slot a 后已刷 boot_a 并 reboot 成功。
实机是否获得来源栈待下一轮读取，尚未正常开机。
整理见 kernel618-slab-r11-{boot,qemu-slab,hardware}.json。
当前五版为 display-r7、display-r8、display-r9、fault-r10、slab-r11；
仅清理旧 display-r6 交付目录，原始日志及源码记录保留。


### slab-r11 实机结果与 AUX 生命周期根因

run 6080c2fc01074de6，seq69/70 至 22.461/23.278 秒，两份 CRC/尾标记有效。
cmdline 的 slab-r11、stack_depot_disable=off 和 slab_debug=U,kmalloc-2k 均确认。
同一设备链表 BUG 再现；本轮成功保存分配栈和 Free path。
坏 entry 为 ffffff8023d7d1e0，所属 kmalloc-2k 对象起点 ffffff8023d7d000、偏移 480。
最新分配来自 sde_hw_sspp_init；保留的上次释放栈为 devm_kfree → dp_aux_put →
dp_display_post_init → dp_connector_post_init → sde_connector_init。
SSPP 是复用已释放对象的后续分配者，不能据此指责它错误释放了 AUX。

源码确认：dp_init_sub_modules 先成功注册 AUX 的内嵌 I2C adapter，再查找 DP PLL；
本机缺少新 qcom,dp-pll phandle，使 PLL 初始化失败，错误路径直接 dp_aux_put。
旧 dp_aux_put 只销毁 mutex 并 devm_kfree，没有注销仍在设备链表中的 I2C adapter。
devres 的 128 字节头 + AUX 对象内 I2C kobject.entry 的 352 字节偏移恰好是 480；
在独立回归模块用相同内核类型和实际结构声明编译断言核对。
所选 nuwa/HyperOS 集成、LOS 92a9fde479d3262da080cfd28bab0775b0da500a、
MiCode 6461221b68908b990e1fa2b60feaa812cb944ef5 都有同样的错误清理遗漏；
MiCode 旧同节点 PLL 绑定避开了本机这条触发路径。现修复对象所有者的清理职责，
不删除链表检查，不用禁用 SSPP 或整个 DP 来掩盖问题。
原始日志 reports/device/kernel618-slab-r11/；结果见 kernel618-slab-r11-hardware.json。


### aux-r12：DP AUX 修复实机越过旧异常，尚未开机

修复 AUX 所有者的释放顺序：成功注册后，先注销内嵌 I2C adapter，再释放对象；
重复注销及注册失败可安全清理，PLL 错误出口清空 dp->aux。
参考来源和固定提交见 kernel618-dp-aux-lifetime-source.json；旧 PLL 绑定及外接显示仍未完成。
QEMU 用实际 DRM/I2C 注册路径验证六种生命周期，全部通过；旧版 put 对照检测到
释放时 adapter 仍存活。相同结构的编译断言核对 128+352=480 的悬空 entry 偏移。
337 模块 ABI、全部归档权限、助手执行和 boot 解包回读通过。

实机 run 0f13ca0f8bfb71ea，seq426/427 为 120.350/120.606 秒，两份 CRC/尾标记有效。
此前 list_add BUG 未再出现；显示 splash、DRM 注册、postinit 均返回，
msm_drm 25.442 秒加载完，GPU msm_kgsl 28.307 秒加载完。
原厂 init 已挂载系统分区，最后动作是 init.qti.kernel.rc:54 的 post-fs；
printk 至 32.631 秒，但日志写入线程继续工作至 120 秒，尚不能判为整个内核硬死锁。
用户看到白闪后卡米标，手动返回 Fastboot；系统启动及功能验证仍未通过。
下一步读取 init 等待原因，并加入仅测试版启用的 180 秒自动回 Fastboot 和电脑端读日志。
原始记录 reports/device/kernel618-aux-r12/，整理见 kernel618-aux-r12-hardware.json。
当前五版：display-r8、display-r9、fault-r10、slab-r11、aux-r12；仅清理旧交付目录。


### auto-r13：仅测试模式的自动 Fastboot 流程

仅 cmdline sheng_bootlog.test_timeout=180 启用：内核运行时间 175 秒打印 PID1 与
不可中断任务栈并落盘，180 秒 kernel_restart("bootloader")。日志窗口延至 200 秒。
普通 kernel_restart 在测试模式统一转 bootloader；emergency_restart 保留同一意图。
按实际 qcom-reboot-reason 的 DT NVMEM cell 预写 0x02，不猜寄存器地址。
异常/直接 panic 在其他 CPU 停止前给跨 CPU 写入及重启留出 15 秒，普通模式仍为 1.5 秒。
10 秒高精度定时器兜底绕过阻塞的设备 shutdown。异常 CPU 关 IRQ 使普通睡眠及
关机等待受阻，已在 QEMU 复现并用独立复位定时器处理；不保证整 SoC 硬锁或过早硬件复位。

相同交付 Image 的 QEMU 普通落盘（无测试参数）、15 秒测试截止、真实 BUG、直接 panic、
普通 reboot 和 emergency_restart 均通过。QMP 明确返回 guest-reset，避免把异常期间
控制台停止输出误判成没有复位。BUG 的寄存器/调用栈和超时前任务栈有 CRC 有效副本。
18,008 内核导出未变，原样复用 r12 的 337 模块 overlay；不重新编译显示驱动。
官方 boot 只读封包、AVB 和解包回读通过。

电脑端 scripts/test_sheng618_hardware.py 仅进行一轮：核对 serial/sheng/slot a/unlocked，
刷 boot_a，等待 USB 离开及自动回 Fastboot，临时 boot 已验证 Recovery，
仅读 rawdump 288..290 MiB，校验 CRC/本轮 cmdline 后返回 Fastboot。
所有调用/等待有超时；失败停止，不循环刷入。若检测到候选 6.18 ADB，记录下一版关闭测试模式。
目前软件验证通过，实机自动 Fastboot 和读回尚待这一轮测试。
用户已要求一旦 ADB 连通，下一版去掉测试模式；默认不传参数即关闭此行为。
五版交付为 display-r9、fault-r10、slab-r11、aux-r12、auto-r13。


### auto-r13 实机自动化通过

本轮无需手动按键：刷入并启动后，电脑在 190.40 秒重新收到 Fastboot，
自动临时启动 Recovery，读取 CRC 有效的 run 268ff7eca5cb8087，
seq651/652 至 179.590/179.878 秒，之后自动返回 Fastboot。
175.106 秒任务栈已保存：PID1 为 S 状态 epoll 等待，不是卡在不可中断内核调用。
结合原厂 rc 和 modprobe 的退出日志，确认等待模块就绪属性这条兼容问题。
Android 尚未启动、候选 ADB 未连接；异常返回 Fastboot 仅 QEMU 验证，实机此次验证超时路径。
自动化记录 kernel618-auto-r13-automation.json，硬件结果 kernel618-auto-r13-hardware.json。


### modules-r14：修复 HyperOS 重复加载旧 ABI 模块的内核兼容

r12/r13 中 6.18 msm_sysstats 和 zsmalloc 已成功加载，原厂 modprobe 随后再次尝试
5.15 文件，先撞上 struct module 布局校验，退出 1。vendor_modprobe.sh 第一模块失败后
直接退出，未发送 vendor.all.modules.ready；init.qti.kernel.rc:54 的 wait_for_prop 无限等待。
这是移植内核与原厂启动约定不兼容，未修改原厂镜像或 rc 脚本。

启用 CONFIG_SHENG_LEGACY_MODULE_REUSE：签名及 ELF 边界、modinfo 校验之后，
仅当旧 5.15 文件声明的模块名已有 MODULE_STATE_LIVE 的驱动，返回原生 -EEXIST；
缺失/未就绪的驱动仍执行完整布局和 ABI 校验并报错。未加载旧机器码，也未伪造所有错误成功。
Android libmodprobe 已有 EEXIST 成功处理，原厂模块脚本可继续完成；参考固定提交见
kernel618-module-reuse-source.json。选定上游 k618_insmod 的泛化错误容忍没有启用。

同一交付 Image 的 QEMU 实际 syscall 验证通过：普通重复 EEXIST、
伪造旧 ABI/错误结构大小但已有 6.18 驱动的重复 EEXIST、相同旧 ABI 但无对应驱动 ENOEXEC。
已加载探针 init 仅执行一次，缺失探针未执行，结果标记实际写入 CRC 有效 rawdump。
337 模块 overlay 与 r12 相同，18,008 导出一致，官方 boot 封包/AVB/解包回读通过。
仍启用 180 秒测试模式（候选 ADB 尚未连接）；此修复实机验证待本轮刷入。
当前五版：fault-r10、slab-r11、aux-r12、auto-r13、modules-r14。


### modules-r14 实机越过模块等待，自动重启重定向有效

run a6d371991c93cd3b，seq132/133 至 43.268/43.552 秒，两份 CRC 有效。
vendor.modprobe 在 39.335 秒以 0 退出，模块就绪属性已置位；init 越过原卡点，
late-fs 成功挂载 /data，40.828 秒进入 post-fs-data。
41.066 秒 vold 的 add_key("fscrypt-provisioning") 返回 EINVAL，per-boot key 安装失败，
init 因 enablefilecrypto_failed 主动请求 reboot,recovery。未见新的 Oops/panic。
测试内核把这次软件重启自动转到 Fastboot，电脑于 55.10 秒收到设备，自动读回再返回。
因此实机已验证超时与软件主动重启两个 Fastboot 入口；异常/panic 仍只有 QEMU 验证。
ADB 尚未连接，保留测试模式。下一步修复 fscrypt ABI 兼容，保持系统包不变，
只诊断负载大小/标志而不记录密钥内容。
详见 kernel618-modules-r14-{hardware,automation}.json。


### crypto-r15：保持返回值不变，只读取 fscrypt 负载元数据

对照 ACK ff4a6c3、LOS f9ca2b71、MiCode 29db5d59：5.15 provisioning 负载第二字段是
reserved，允许至 128 字节；所选 6.18 将该字段定义为 flags，未标 wrapped 时最多 64 字节，
get_keyring_key 还要求 payload.flags 与 ioctl flags 一致。实际负载尚未确认，不能先放宽校验。
新增长度、头长度、type、flags、raw 长度的诊断，无密钥、标识符或原始负载打印；
所有原校验和返回值保持不变。source receipt 为 kernel618-fscrypt-trace-source.json。
复用 r12 模块和 r14 兼容修复，18,008 导出、官方 boot 封包及解包回读通过。
不重复与纯诊断打印无关的 QEMU 生命周期测试；接下来实际读回元数据，再决定 ABI 修复。
仍保留 180 秒测试模式，实机结果待本轮自动读取。
当前五版：slab-r11、aux-r12、auto-r13、modules-r14、crypto-r15。


### crypto-r15 实机确认旧 wrapped 负载 ABI

自动读回 run a293e563889714e0，实际元数据：len=108、header=8、type=2、flags=0、raw=100。
这是旧 5.15 的零 reserved 头表示的 100 字节硬件封装密钥，新 6.18 把它按普通原始密钥
64 字节上限拒绝，实机证据与源码差异吻合。未打印密钥内容。
下一修复只兼容旧 provisioning 表示；取用时仍要求旧 ioctl wrapped 标志，
新接口的 raw/wrapped 区分与尺寸校验保持严格。当前 ADB 未连通、系统尚未开机。
此次自动返回 Fastboot、临时 Recovery、读取日志和返回 Fastboot 再次完成。

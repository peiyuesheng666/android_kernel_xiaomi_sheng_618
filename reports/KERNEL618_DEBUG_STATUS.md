# sheng 6.18 实机日志与启动调试

日期：2026-11-08。用户授权封包、刷入和直接测试；不备份当前 boot，
官方刷机包只读，生成版本最多保留五版。仅测试 boot_a，未刷 init_boot、
vendor_boot、super 或 userdata；临时启动已验证的 r13 Recovery 读取证据。

## 当前实机结果

disklog-r5 已成功把本机 6.18 日志写入 rawdump，并经 Recovery 读回。
两份 CRC/尾标记均有效，同一 run `22f635d504b39522`：

| 序号 | 时间 | 日志长度 |
| --- | --- | --- |
| 29 | 12.419 秒 | 251,998 字节 |
| 30 | 13.273 秒 | 261,644 字节 |

第一处明确异常发生在 12.378560 秒，空地址 `0xa50`，PC 为
`dsi_display_get_default_lms+0x70/0xdc [msm_drm]`。调用经过
`_sde_connector_lm_preference`、`sde_connector_init` 和 `sde_kms_hw_init`。
此前已经注册 UFS 分区并加载到批次第 228/233 个显示模块；不能据此认为
所有模块、USB、存储加密或显示功能正常。快照包含 Oops 和部分调用栈，
没有记录最终 panic 或重启原因。

原始证据仅保留本地：`reports/device/kernel618-disklog-r5/`，含刷写输出、
两份原始区域、解码元数据和日志。整理结果及哈希见
`kernel618-disklog-r5-hardware.json`。

## 显示模式表修复（display-r6）

对照所选 6.18 基座、LOS 模块提交
`92a9fde479d3262da080cfd28bab0775b0da500a` 和 MiCode sheng display 提交
`6461221b68908b990e1fa2b60feaa812cb944ef5`：`get_default_lms` 的基本遍历
在三者相同；MiCode 额外处理 `mi,video-mode-multi-timing` 和每个 timing
的 `mi,mdss-dsi-supported-fps-list`，通用基座没有处理这些属性。

本机实际 DTB 中，活动面板有三组时序：120 Hz 时序支持 120/60，144 Hz
时序支持 144，90 Hz 时序支持 90/50/48/30。旧逻辑按全部时序分配 21 项，
随后只构造第一时序的 7 项，遍历剩余空项时崩溃；还会错误地用 120 Hz
时序推算 144 Hz 的 porch。不是靠跳过空指针来替代时序适配。

修复保留现有 6.18 驱动，读取上述原厂属性以构造完整七项表；增加写入边界、
最终数量检查，并将失败后释放的 modes 指针清空。属性数据由原 parser 持有，
随 mode 私有信息复制引用，不新增 FPS 数组堆分配。没有引入其他型号屏幕参数。
模块去掉调试符号后封入原模块层，日志代码保持原样。

来源与源码前后哈希：`kernel618-display-multitiming-source.json`；实际 DT
只读审计：`kernel618-display-multitiming-dt.json`；337 个模块和 20,544 项
导入 CRC 检查通过：`kernel618-display-r6-layer.json`。

### r6 封包错误与 r7 实机结果

r6 运行至 120 秒，但 /k618_umh 以 -13（权限拒绝）执行失败：233 个后续模块
全部未尝试，不能用于判断显示修复。mkbootfs 的 Android fs_config 将助手
0755 改成 0644。r7 改用 GNU newc cpio；349 项路径和权限全部与原模块层相同，
337 个模块中仅 msm_drm.ko 负载改变，助手字节完全一致、权限 0100755。

r7 复用 r6 已构建的显示模块，未重复编译。QEMU 使用实际 r7 内核解出并执行
内嵌助手、加载 virtio 模块和真实写盘，两份 CRC 快照通过；负面分区测试沿用
未改变日志实现的 r5 结果。见 `kernel618-display-r7-layer.json` 和
`kernel618-display-r7-qemu.json`。

r7 已刷入 boot_a。经临时 r13 Recovery 读回 run e406b6c7f30277d3 的 seq31/32，
分别至 12.215/12.516 秒，CRC/尾标记有效，cmdline 确认为 sheng_test=display-r7。
模块加载不再报权限错误，已到第 228/233 项 msm_drm；12.324783 秒成功建立
7 modes from 3 timings，随后继续初始化，越过 r5 的 get_default_lms 空指针位置。
仍未正常开机，快照没有新的 Oops/panic；不能认定显示整体功能已恢复。

日志包含 DP PLL 缺失 qcom,dp-pll phandle、HFI shared buffer -22 和 SPR version 0。
只读对照原厂/LOS 源码及正常 Recovery：原厂 DP 使用同节点 qcom,pll-revision，
Recovery 正常识别 DP_PLL_4NM_V1_1。这证明绑定不一致，但不足以断定停机原因。
原始日志在 reports/device/kernel618-display-r7/；下一步细化显示初始化检查点。

### r8 显示阶段检查点（实机日志已读回）

新增 sheng_boot_trace.h 与 display-probe-trace.patch，限定在可休眠的显示 probe
上下文记录硬件初始化、连接器、每个 CRTC、IRQ、mode reset、splash handoff、
DRM 注册和 postinit 的前后阶段。每次检查点等待 350 ms，给原 250 ms 工作队列
保存日志的时间；会增加启动时间并可能影响时序，属于诊断候选。
没有依据现有的错误行直接禁用 HFI/DP 或宣称修复新的停机问题。

源码与固定参考记录见 kernel618-display-probe-trace-source.json。显示模块编译、
337 模块的 20,544 项导入 CRC、18,008 内核导出、349 项归档路径/权限、只改变
msm_drm.ko 负载和官方 boot 解包回读均通过。编译模块中检查点字符串与源码
哈希已核对，未重复运行不能覆盖该模块硬件行为的 QEMU 测试。

boot SHA256: 21a41ee11c30437a712db6891d319359cf65eebe774bcfbaf8ed59014551b893。
Image SHA256: b5d2b44b566ac85bd704b50b5c63c2c13d2f07cca6e288d34d0e9b63950a4efb。
已经 Recovery ADB 重启到 Fastboot 后刷入 boot_a 并发出 reboot，命令均成功。
用户反馈仍失败。读回 run 96341b5145998f87，seq69/70 至 22.141/22.397 秒，
两份 CRC/尾标记有效，启动标记为 display-r8。
六个 CRTC 创建均返回 error=0，硬件/VM 初始化、IRQ 安装、mode_config_reset
均返回。22.146553 秒为最后记录的 mode_config_reset returned；未保存后续
cont_splash_config begin 或最终显示异常栈。HFI/SPR 报错后这些步骤仍然完成，
不能把它们当作已证明的终止原因，也不能认定尚未保存的下一阶段从未执行。

### r9 旧画面接管对照（未改善，日志已读回）

所选底座固定提交 c3956156ce7c4193c451dfda531fad72d35bfebb 的 k618_timg.sh
已有 msm_drm.k618_cont_splash 开关（其临时启动默认 0）；k618_tp_fix.py 的实现
在关闭时保留 splash 内存一对一映射，清除旧画面交接状态，让后续流程重新点屏。
k618_load.c 从实际 kernel cmdline 提取模块参数后传给 finit_module。
这是底座现有调试路径，未因此引入其他机型面板参数。

r9 完全复用 r8 Image（SHA256 相同），仅改变 boot cmdline 的测试标记和
msm_drm.k618_cont_splash=0，用于判断旧画面交接是否影响后续进展。
未重复编译内核/模块；原厂 boot 只读，AVB 自校验和内核解包回读通过。
boot SHA256: b28a199244fa644433ba8acbcc2f7c9da711ed7d684cce2151c4f5ae0b56a09d。
用户反馈仍失败。读回 run 34ce03b2b23a7c35，seq69/70 至 22.077/22.329 秒，
两份 CRC/尾标记有效。模块参数 k618_cont_splash=0 和内核日志 none handed over
均确认开关生效，但最后阶段仍为 22.113900 秒 mode_config_reset returned。
该选项未解决启动失败；不能据此补造最终崩溃位置或认定已经完成正常冷点屏。

### r10 异常寄存器/调用栈落盘（实机已抓到终止异常）

r8/r9 都缺少最终故障栈。保留 r8 的显示模块、权限和阶段检查点，ARM64 __die
打印 show_regs/dump_kernel_instr 后调用一次有界抓取窗口；此处只排队另一颗在线
CPU 的高优先级工作并等待 1500 ms，不在异常上下文做块 I/O 或获取日志互斥锁。
普通与异常工作以互斥锁串行访问同一缓冲、序号和文件，偏移仍为 rawdump 288..290 MiB。
非 SHENG_BOOTLOG 配置使用空内联函数，18,008 个内核导出/CRC 保持不变。

第一版模拟故障证明单纯延时无法保存最终栈：定时任务可能绑在关中断的故障 CPU。
该未刷候选已在保护检查下原位替换；改为明确向其他 CPU 排队后重新编译。
最终 QEMU 测试在 CPU1 的临时模块中 BUG，panic_on_oops=1，存储 IRQ 在 CPU0；
读回两份 CRC 有效记录，最新至 13.435 秒，包含故障模块、PC、Call trace 和抓取窗口。
故障模块仅存在于临时测试 initrd，不包含在平板交付 Image 的模块层。
正常场景执行实际内嵌 /k618_umh 加载 virtio、写盘/fsync 成功；错误 GPT 名称、
299 MiB 大小均拒绝写入，损坏一份后另一份仍可读。见 kernel618-fault-r10-qemu.json
和 kernel618-fault-r10-qemu-fault.json。

限制：真实故障必须进入 __die，且其他 CPU 与存储中断仍能工作；不保证捕获硬件
整体挂死或直接 panic 的路径。模拟测试不等于真实 UFS 异常抓取通过。
源码与补丁见 kernel618-fault-capture-source.json、sheng_bootlog.c/h 和
arm64-fault-capture.patch。boot 封包、解包回读、AVB 自校验、原模块层哈希核对通过。
boot SHA256: bcdef4a1f306623ee176b3f54ed94693a1bfa6ef135a361bebc1b3c48c2fee9f。
Image SHA256: 99d34cdb44cf1174c23451aad863adbc459d728268c509ca4905c632285e8f6a。
已刷入 boot_a，实机已保存设备链表 BUG 的完整异常栈，见下方结果；尚未正常开机。

## 内核直接落盘

`sheng_bootlog.c` 内置于内核，在 late_initcall 启动工作队列，保留 Android
原 init 和原模块层。无需 USB、额外用户进程、挂载文件系统或 /dev 节点。
仍需 UFS 与 GPT 分区注册完成；过早崩溃无法写盘。

- 只接受 GPT 名称 `rawdump`、大小恰为 314,572,800 字节的已打开分区。
- 只在该分区偏移 288..290 MiB 写入，轮换两份 1 MiB 快照。
- 约每 250 ms 保存一次 printk，并 fsync；最多运行 120 秒。
- 日志缓冲区为 4 MiB，单份保存至多约 1 MiB 最新日志。
- CRC 与尾标记用于拒绝未写完的记录；不在 panic 上下文同步写盘，可能遗漏最后部分。
- 已先读取上述 2 MiB 原内容用于比较；这不是当前 boot 的备份。

构建信息见 `kernel618-disklog-r5-boot.json`。18,008 个内核导出与 CRC
保持不变，官方 boot v4 封包、ARM64 头、解包内核回读和 AVB 自校验通过。
AVB 使用 NONE，仅为已解锁设备的开发候选。

`test_sheng618_disklog.py` 使用实际 AArch64 内核和临时 GPT 虚拟磁盘，
完成真实块写入与 fsync：正确分区产生两份可读快照，错误名称/大小拒绝写入；
损坏一份后另一份仍可读。首次测试缺少 virtio PCI helper，随后修正加载顺序；
用户日志标记由 write 写入 /dev/kmsg，避免 glibc dprintf 在该设备上的失败。
通过结果见 `kernel618-disklog-r5-qemu.json`，不把模拟结果当作 UFS 硬件证据。

构建：`python3.11 scripts/build_sheng618_disklog_boot.py`（一次性版本，拒绝覆盖）。
解码：`python3.11 scripts/read_sheng618_disklog.py <region.bin>`。
读取命令仅操作 Recovery 临时文件和已确定区域：

```sh
dd if=/dev/block/by-name/rawdump of=/tmp/sheng-bootlog.bin bs=1048576 skip=288 count=2
```

## 之前的 USB 尝试

| 版本 | 结果 |
| --- | --- |
| serial-r1 | 前置 PID1 加载 USB 模块并等待主机，改变启动现象，未收到端口 |
| baseline-r2 | 官方容器仅换原始 Image，用户确认复现白闪、米标、黑屏 |
| serial-r3 | 后台串口进程立即交还原 init，现象恢复，未收到端口 |
| serial-r4 | 修正先请求 peripheral、后等待 UDC 的顺序，仍未收到端口 |
| disklog-r5 | 不加入 USB 前置进程；日志落盘实机成功，取得显示驱动 Oops |

用户桌面 boot 单独临时启动可进入 HyperOS，实际枚举为 ADB，未见 COM。
USB 参考仓库固定于 `8095782bddbb9e9a74a4b5aaf9b9aef82c743ebb`：
init_boot 的 /init 转交 vendor_boot 的探测程序，再由其设置 USB ACM。
最新参考刷写脚本仅刷 vendor_boot_a，依赖此前配套的 init_boot。
本任务仅参考 USB 顺序和描述符，没有引入 HarmonyOS 服务。
文件与哈希见 `kernel618-anyhmos-usb-reference.json`。

当前五版保留为 display-r7、display-r8、display-r9、fault-r10、slab-r11。
首版及 baseline-r2 交付目录已清理，原始 Image 仍保留在 WSL
/root/sheng-618/diagnostic/baseline-r2/verified/kernel。


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


### wrapped-r16：兼容旧 Android wrapped provisioning ABI

CONFIG_SHENG_LEGACY_FSCRYPT_PROVISIONING 允许旧零 reserved 负载存入至 128 字节；
取用时只有既有 Android ioctl 的 __flags 合法置位后，secret.android_compat 为真，
才允许把零 reserved provisioning 解释为 wrapped。新 flags 接口继续严格检查 raw/wrapped
匹配；新增取用时的实际长度校验，普通原始密钥仍受 64 字节限制。
复用所选 ACK 原有 Android 旧 KDF context 和硬件导出逻辑，不修改密钥、磁盘格式或系统包。
来源及实机触发证据见 kernel618-fscrypt-legacy-source.json。

同一 Image 的 QEMU 用公开的合成字节，通过真实 add_key 系统调用七例和 ext4
FS_IOC_ADD_ENCRYPTION_KEY 七例。正常原始密钥成功；旧零 reserved 100 字节及新
wrapped 100 字节均通过负载检查，进入虚拟硬件不支持的 wrapped 派生层并得到 EOPNOTSUPP。
错标类型/flags、过长过短负载、新 raw 取用 100 字节、未经旧 __flags 的错误 wrapped
取用、两组 wrapped 标志冲突均按预期拒绝。不是用假驱动证明硬件解密有效。
结果标记已落入 CRC 有效快照；QEMU 不具备真机 ICE，真实 wrapped 派生仍待实机。
18,008 导出及官方 boot 封包解包检查通过，337 模块仍复用 r12，不重编显示模块。
保留 180 秒测试参数；实机 ADB 尚未连接，本轮准备自动验证。
五版：aux-r12、auto-r13、modules-r14、crypto-r15、wrapped-r16。


### wrapped-r16 实机通过加密初始化，panic 自动回 Fastboot

run 7c9c618cd9fdeff7，seq152/153 至 43.564/43.826 秒，CRC 有效。
旧 100 字节 wrapped provisioning 已接受，42.261 秒 enablefilecrypto 以 0 退出；
既有加密目录校验、持久属性、APEX 和 init_user0 均已继续，真实硬件加密路径通过本轮启动阶段。
尚未验证所有凭据解锁与完整 Android 功能，候选 ADB 仍未连通。
下一故障是 kiwi/amss20.bin 固件直读 ENOENT，sysfs fallback 被 firmware_load 权限拒绝，
43.812 秒 CNSS 触发 wlan crashed panic。异常栈已持久保存。
电脑在 64.74 秒自动收到 Fastboot，自动临时 Recovery 读日志后再次返回 Fastboot。
因此超时、Android 主动重启、实际内核 panic 三种回 Fastboot 路径均已实机验证。
全 SoC 硬锁或极早复位仍不能保证。保留测试模式，ADB 连通后的下一版关闭。
详见 kernel618-wrapped-r16-{hardware,automation}.json。


### firmware-r17：恢复原厂 firmware SELinux 加载接口

官方 modem 镜像提取目录存在 kiwi/amss20.bin，原厂 ueventd 指定了 firmware_mnt/image
与小米 Wi-Fi APEX 搜索目录。r16 在 modem_a 挂载完成后直读 ENOENT，用户态补载被
SELinux 的 system:firmware_load 拒绝，随后 CNSS panic；不是固件缺失。
对照固定提交的 LOS 与 MiCode 5.15，两者的 SELinux read/load hooks 只检查模块，
没有 6.18 新增的 firmware_load 检查。CONFIG_SHENG_LEGACY_FIRMWARE_LSM 仅恢复
READING_FIRMWARE/LOADING_FIRMWARE 的旧行为，正常文件与 sysfs 权限、其他加载类型、
其他 LSM 和 IMA 检查继续运行。SELinux 强制模式及原厂策略不修改。

真实 AArch64 QEMU 对照：使用相同的强制策略明确拒绝 firmware_load；r16 直读返回
EACCES、补载被拒，r17 直读与 sysfs 补载均成功且数据逐字节一致；缺失固件仍 ENOENT。
两版均验证专门拒绝的 sysfs 文件读取 EACCES、finit_module 的 module_load EACCES。
各三例 firmware 请求与两例权限拒绝全部通过，标记落入 CRC 有效日志。
不是关闭 SELinux，不禁用 Wi-Fi，不改原厂固件。18,008 导出不变，337 模块继续复用 r12。
官方 boot 封包、AVB 和解包回读通过，保留 180 秒测试模式；实机启动待本轮自动验证。
当前五版 auto-r13、modules-r14、crypto-r15、wrapped-r16、firmware-r17。


### firmware-r17 实机首次完成原厂系统启动，显示与 USB 待修

用户确认进入系统，同时报告花屏与 USB 异常。CRC 有效实机日志在 79.076 秒出现
sys.boot_completed=1，原卡住的固件补载恢复，GPU/ADSP/Wi-Fi 配置已由原厂 ueventd 传入。
不等于所有功能正常：USB 在 adbd 启动后持续报无可用 UDC，显示切换 50/120Hz 但花屏，
另有 Wi-Fi NAPI 清理警告，Wi-Fi 功能未验收。候选 ADB 从未连通，继续保留测试模式。
180 秒计时后自动回 Fastboot，主机 198.92 秒收到，临时 Recovery 自动读回两份日志。
日志量超过 1 MiB 后开头命令行被尾部快照挤出，脚本因此停止，未自动完成最后回退。
原始快照未丢失，已显式解码、验证 CRC，并回到 Fastboot；未取消或放宽校验静默认领。
run668e360a40eda214，seq576/577，uptime179.234/179.539 秒。版本归属依据本轮唯一受控
flash 的哈希、全新 run 与超时范围，快照本身没有版本标记；下一版增加持续版本身份。
详见 kernel618-firmware-r17-{hardware,automation}.json。


### usb-r18：补齐 sheng PS5169，测试窗口延长至十分钟

r17 实际 DT 的 ssusb_redriver 指向 mi,ps5169（a80000.i2c/ps5169@28），
原 337 模块包没有此驱动，redriver core 因找不到 provider 返回 EPROBE_DEFER。
选定 6.18 底座的 NB7VPQ904M 只参考新回调语义；LOS SM8550 无此平板驱动，
使用获授权的 MiCode sheng 29db5d59 的 PS5169 原寄存器配置，适配 I2C/class API、
控制器方向和三参数 DP release 回调，不导入已不存在的充电属性 ABI。
外接 DP 功能不作可用声明。保留 r12 显示模块及原有 337 模块，仅增加 PS5169。
338 模块共 20,574 项版本化导入通过，18,008 内核导出保持不变。

按用户要求设置 600 秒测试超时，日志生命周期 620 秒，主机等候上限 655 秒；
已有异常/软件重启回 Fastboot 行为保留。候选 6.18 ADB 连通后每 60 秒读取
属性、dmesg、logcat 和 USB/DRM 状态；下一版取消测试模式。
原厂系统和固件树未修改，仅封包 boot_a，原厂 boot 解包回读和 AVB 验证通过。
同时为每秒快照补版本和 run 身份，读取时必须与 CRC 头部 run 匹配。
真实 AArch64 QEMU 已写入超过 1 MiB 日志，确认最初命令行被挤出后，
两份 CRC 有效快照仍保留匹配身份；真实 helper 执行和模块装载通过。
实机 USB、花屏和十分钟超时结果仍待本轮验证。
交付目录最多五版：modules-r14、crypto-r15、wrapped-r16、firmware-r17、usb-r18。


### usb-r18 实机 ADB 连通，新增板级故障与十分钟复位限制

实机 6.18 ADB 于 2026-11-08 23:52:04 +0800 连通，sys.boot_completed=1，
USB service 回读 connected/configured=true，已保存六轮属性和 logcat。
后续连接中断，不能认定 USB 稳定。用户明确反馈色块/乱码/撕裂、触摸失效、
自动旋转失效和扬声器无声。InputManager 没有触摸屏，SensorService 没有实体传感器，
FastRPC 旧节点缺失；这些均未适配完成。不能把启动成功当作全部硬件通过。
600.079 秒确实执行测试复位，但主机 655 秒未收到 Fastboot，需用户手动进入。
日志停在600.108秒的充电驱动 shutdown 阶段，未证明十分钟自动复位成功。
临时 Recovery 读回两份 CRC 有效日志，run7d62ad27af00f00e，seq2096/2097。
持续版本身份有效，读取后自动返回 Fastboot。后续按约定取消测试模式。
详见 kernel618-usb-r18-hardware.json；原启动控制失败输出保留于本会话，
automation.json 是手动返回后的 readback-only 回执，不应当作原轮完整控制记录。


### panel-r19：N81A DSC 首行参数恢复，取消测试复位

MiCode sheng 6461221b 的 is_use_nt37705_dsc_config 对本机 mi,panel-id
0x4e38316150360200 选择 first_line_bpg_offset=13，通用底座为12。
在派生 RC 参数计算之前恢复该板级分支；其他面板和 DP 保留原入口与行为。
实际编译执行两套公开 C helper，以本机1524x2032/762x16、8bpc/8bpp输入，
scr0/scr1均得到与 MiCode 逐字节一致的完整 drm_dsc_config，
包括dec_delay=669、nfl_bpg=1775和scale_inc=433。不是只改最终PPS一字节。
338模块导入检查通过，只替换显示模块，PS5169和此前修复保留。
原厂boot封包、AVB、解包回读和18008导出一致性检查通过。
因为r18候选ADB已实机连通，本版不传test_timeout和panic测试参数，
保留120秒诊断日志，不再自动重启或把正常软件重启转Fastboot。
实机花屏是否改善尚待刷入验证，触摸/传感器/音频问题未在本版修复。


### panel-r19 实机与视频反馈

实机 ADB 57.26 秒连通，Android 启动完成 86.98 秒；测试复位已关闭。
用户确认花屏改善，但首次启动仍整屏损坏，熄屏重亮后大幅改善，偶发规则横条仍在。
已逐帧查看 IMG_4022.MP4：约1.2秒亮屏，约3.0秒出现规则条纹，约4.2秒恢复。
这些现象不等于已确定根因；继续对照首次亮屏和刷新率切换的板级序列。
触摸、自动旋转、扬声器仍未通过。InputManager无触摸屏，SPI0.0未绑定驱动；
SensorService没有实体传感器，原厂FastRPC节点缺失，音频日志仍将CS35L41路由留在stub。
临时Recovery读回run4a5a4b405171f7ef、seq387/388、至120.548秒，两份CRC有效；
读取后回到Fastboot。详见kernel618-panel-r19-{hardware,automation}.json。

### tablet-r20：恢复 N81A 变帧序列和旧 FastRPC 接口

对照 MiCode sheng 6461221b，补回首次 POST_ON 后的专用视频时序命令、
VRR kickoff 前的扫描有效窗口等待、60Hz 切出时的 pen-clear/vblank 序列，
以及 kickoff 后的专用视频时序命令。仅实际 N81A 面板 ID 启用；全部寄存器负载
仍由本机原厂 DT 解析，保留 r19 的 DSC 数学参数。视频约3秒出现规则条纹、
约4.2秒恢复，仅作为定位依据，尚不能认定已确定全部显示根因。

复用用户指定底座 c3956156 的 k618_rpc515.sh/fix.py，源自固定 fuxi
7fad87dc，适配原厂 qcom,msm-fastrpc-compute 及 adsprpc-smd 接口；
实际 sheng DT 无旧 ION 节点，核实后才采用上游对不再导出的 CMA 查询处理。
EVA 同步使用旧 FastRPC 头重新构建。保留源文件前后哈希、移植补丁和 Kbuild。
338模块、20551项版本化导入检查通过；归档模式与文件表保持一致，只有
msm_drm/frpc-adsprpc/msm-eva 三项负载变化。18008内核导出不变，
官方boot封包、AVB和解包回读通过，测试自动重启关闭，交付最多五版。
DSC 原始 C 数学对照重新执行通过。实机显示、传感器、音频结果待验证。
触摸驱动与 CS35L43 音频路由未在本版补齐，不能声明全部硬件已恢复。


### tablet-r20 实机：传感器恢复，USB 再次断开

2026-11-09 00:28:22 +0800刷入boot_a，55.22秒ADB连通，63.25秒完成Android启动。
旧adsprpc-smd/secure节点和compute上下文均出现，SensorService枚举54项，
加速度计/陀螺仪有真实采样，device_orient有两次事件，WindowOrientationListener
成功订阅方向传感器；实际旋转效果仍待用户验收。锁屏系统截图合成正常，
不能据此证明物理面板横条已修好，N81A命令执行日志尚未读回。触摸仍无驱动。
00:31:48回读前发现USB再次离线，电脑无ADB/Fastboot，未执行reboot或临时Recovery。
不能认定USB稳定或内核死机，正等待屏幕状态与手动Fastboot以读持久日志。
扬声器仍待六路CS35L43机器驱动路由适配；本轮未更改原厂系统和其他分区。
证据及限制见kernel618-tablet-r20-hardware.json，测试自动重启保持关闭。

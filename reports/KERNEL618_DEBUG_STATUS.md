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


### slab-r11：只对已证损坏的内存池记录来源（已刷入，实机待确认）

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

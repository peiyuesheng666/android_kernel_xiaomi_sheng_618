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
导入 CRC 检查通过：`kernel618-display-r6-layer.json`。实际启动结果待下一轮读取。

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

当前五版保留为 baseline-r2、serial-r3、serial-r4、disklog-r5、display-r6。
首版独立 Image 目录已清理，其相同二进制仍包含在 baseline-r2 boot 中。

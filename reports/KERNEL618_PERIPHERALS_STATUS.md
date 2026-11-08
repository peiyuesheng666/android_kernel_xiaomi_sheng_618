# 6.18 sheng 外围实机修复

## 2026-11-09 r21 结果与 r22 触摸修复

r21 在 57.34 秒收到实际 6.18 ADB，65.22 秒完成 Android 启动。
原厂系统和强制 SELinux 保持；无测试超时、无自动重启。

用户确认触摸、手写笔仍不可用，并报告扬声器间歇卡顿。
不能把 `/dev/xiaomi-touch` 出现或模块注册当作触摸恢复。
`spi0.0` 没有绑定驱动，NVT 触摸和笔输入均未出现。

只读原厂设备树的 novatek@0 列出 panel=<0x747 0x74e 0x74f>。
0x747 为通用 Visionox 节点，无 sheng 的 mi,panel-id；后两项才是
N81A，ID=0x4e38316150360200。r21 移植新增的保护只检查第一个
phandle，提前返回 ENODEV。r22 改为遍历该触摸节点的完整 panel 列表，
只接受可用且 ID 精确匹配的 N81A，并记录命中的索引或拒绝原因。
保留 sheng 固件名、SPI/笔功能及板级范围限制。

来源已在 kernel618-touch-source.json 固定 MiCode piano-w-oss 提交
6957f6b646d1c919e175e6f9000eb50c8635273c；它提供同一 NT36532 THP
和笔协议实现，但其面板列表与 sheng 不同，不能照搬首项假设。
nuwa/通用 SM8550 底座没有 sheng 的这组 THP 绑定；以本机原厂 DT 为准。

r21 六颗 CS35L43 已在 secondary TDM RX/TX 链接，六颗均有固件加载记录。
这不证明连续播放正常：AudioFlinger 抓到 fast mixer underruns=105、
overruns=972，logcat 记录 AudioOut_D 一轮 65.66ms，预期 20ms。
暂未确认瓶颈在调度、PCM/DSP 还是其他路径，不先修改缓冲或功放时钟。
原始日志在 reports/device/kernel618-peripherals-r21/；整理哈希与结果见
kernel618-peripherals-r21-hardware.json。

r21 日志已通过临时启动已验证 Recovery 读取：run=dd9aec1354313193，
CRC 有效两份，末次 uptime=120601ms，已返回 Fastboot。
第一次 ADB reboot 调用超时但设备实际进入 Fastboot；第二次从 Fastboot
完成读回，失败记录保留。

r22 编译、340 模块的 20785 项版本化导入、18008 内核导出、
cpio 权限、官方 boot 模板封包/AVB/解包回读均通过。
与 r21 相比只替换两份触摸模块，未改音频；实际触摸/笔效果待验证。
新增直接构建外围模块脚本，避免上游手机补丁重放覆盖已适配源码。
普通测试脚本刷写前会有界等待 Fastboot 枚举。

## r22 实机与 r23 ABI 修正

r22 已实际绑定 spi0.0，注册 NVTCapacitiveTouchScreen、M80p 和 P81c，
Android/ADB 正常启动，但用户实测触摸和笔仍完全无响应。
读回发现 xiaomi_touch_dev_read 持续报 `error count 520 to read, need 1032`。
原厂驱动反汇编 xiaomi_touch_dev_read:0x3354 比较 0x208（520），
MiCode piano 新版 common_data_t 的 data_buf 却有 256 个 s32，结构为 1032 字节。
这是移植源码与本机 HyperOS 的另一处确定 ABI 差异。

r23 将公共命令恢复为 128 个 s32（结构含头共 520 字节），在编译时断言
common_data_t=520、hardware_param_t=214，并限制生产者写入长度，防止越界。
尚不能仅凭这处修复认定原厂 THP 的其他协议均兼容，继续实机验证。

r22 两份 rawdump 快照 CRC 有效，run=eb423662157b76ca，sequence=395/396，
uptime=120310/120600ms。巨量重试日志挤出了周期版本身份，自动工具按原规则
拒绝认领，未放宽校验。原始 region-after.bin 和失败记录保留；上述错误由受控
r22 刷写与此次唯一运行关联，不能声称快照带有 r22 身份。已手动从临时 Recovery
返回 Fastboot。r23 同时给每份快照尾部保留 CRC 覆盖的版本/run 身份，避免日志
风暴再次挤掉身份；槽位格式、分区校验和写入范围保持原值。

r21/r22 的音频卡顿尚未修复；触摸服务反复读取失败可能增加负载，仅列为待验证
因素，不把它写成已确认的音频根因。

## r23 实机与 r24 帧长度修正

r23 59.66 秒连上实际 6.18 ADB，67.04 秒记录系统启动完成。
原厂 HAL 的 common 命令已经正常处理，不再因 520/1032 差异忙重试。
用户实测触摸仍不可用；不得把中间接口修好当作触摸功能恢复。
119.66 秒的 /proc/interrupts 显示 xiaomi_tp 已有 1201 次中断。
内核却持续丢弃 crc_len=0x4bb 的包；包内校验字段与各自反码一致，
失败来自源码硬编码只接受 piano 的 0x4c3/0x50d。

只读原厂 nt36532_touch.ko 反汇编 nvt_ts_work_func：0x9664 比较 0x505，
0x966c 比较 0x4bb，0x9674..0x9684 保留 checksum/length 反码检查。
r24 精确恢复 sheng 的这两个长度，不扩大接收任意长度，不跳过校验，
不替换原厂固件。r23 在 70.193 秒成功装入本机 n81a CSOT 固件，
FW=0x13、PID=0x5981，frame_len=5160；并非固件不存在或 SPI 无数据。

r23 rawdump 自动读回并返回 Fastboot 成功，run=836f66062bced21a，
末次 uptime=120578ms，版本/run 尾标记与快照 CRC 有效。
同一 r23 Image 的 AArch64 QEMU 实际 GPT 写入/fsync、双槽 CRC、
破损副本拒绝、命令行被挤出后身份尾标记均通过。
只跑了此次变更相关正例/回卷测试，未重跑既有分区名称/大小拒写测试。

r24 编译、340 模块 ABI、18008 导出、原厂 boot 封包解包检查通过。
boot SHA256=805aab1554cc394c6d1d41a87c160c000910e5a45eab1e5c71ed97150ddb5759，
Image SHA256=ef45268d3995d2be3991e3b53d3c508c124898c42f813e67ab3b4cb3a2d1ed32。
已刷 boot_a，实际触摸和笔验证仍在进行，音频卡顿未宣布修复。
交付目录最多五版，正常版本均未启用自动重启。

## r24 用户确认触摸、笔恢复

r24 59.28 秒连上 ADB，65.03 秒记录 Android 启动完成。
用户明确反馈“都可以了就是触摸启动的有点慢”。记录为手指点击、笔落笔
基本功能已由用户验收；压力/倾斜/按键、休眠唤醒与长期稳定性尚未完整验证。
实际 dumpsys input 已有手指坐标变化，getevent 也记录到手指输入。
25 秒监测窗口中未记录到两支笔设备的事件，不据此推翻用户实测，也不虚报
已抓到笔的完整坐标轨迹。

仍有触摸启动慢、开机白闪、键盘/触摸板等未完成问题。
r24 THP HAL 偶有 `copy_frame_data_from_mmap:err tp_frame crc error`，
暂未区分环形缓冲并发读取或其他原因，不能把基本可用写成完整无故障。
扬声器需持续播放复测；准备抓取时 ADB/Fastboot 均不可见，已询问 USB
连接情况，尚不能归因 USB 驱动或断线。没有因此开启自动重启。

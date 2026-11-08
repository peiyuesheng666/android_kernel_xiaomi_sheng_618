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

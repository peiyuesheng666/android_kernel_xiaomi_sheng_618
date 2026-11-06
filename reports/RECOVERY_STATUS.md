# 2026-11-06 Recovery 实机检查点（北京时间）

当前已刷入 r13：显示、全屏点击、源码内核、misc 修复和触摸启动提速均已实机验证。

## 最新 r13 结果

- 镜像 SHA256：738556589abb2c35047879f14cfed63a05a6ed25c7c418a0209709622312376f。
- 已刷入 recovery_a，发送/写入/reboot recovery 全部 OKAY；ADB 确认 variant 为
  r13-native-source-fast-touch，内核为 5.15.220-gf9ca2b71f672，旋转属性为 ROTATION_RIGHT。
- 原厂触摸模块的 nvt_ts_probe 中，固件 work 的等待写死为 3500 jiffies，
  当前 HZ=250，即 14 秒。在 Recovery 模块副本中将这一条 MOV 指令改为 250 jiffies（1 秒）。
  精确校验输入 SHA、ELF 符号、调用重定位与指令上下文；仅一条指令变化。
  固件回调、锁、vermagic、导入/导出 CRC 与所有其他字节保持一致。
- 修改由 scripts/patch_recovery_touch_delay.py 可重复生成，随 r13 源配置归档保存。
- 实机触摸固件就绪从 r12 的 18.007897 秒降为 r13 的 4.858837 秒。
  程序在 4.251030 秒启动；模块真实 SHA 与候选一致，未出现符号或 CRC 加载错误。
- 用户明确确认“很快响应，点击位置正常”；Recovery、触摸服务、ADB、misc 均正常。
- 检查证据：reports/recovery-r13-hardware-verification.json 与
  reports/device/flash-recovery-20261106-070838/r13-diagnostics.txt。
- 整包 LineageOS 开机测试尚未完成。用户现准备安装原来的 A/B OTA ZIP，
  需核对 payload 中的旧 Recovery，避免将它当作 r13。

以下为 r12 基线记录，用于对比。

## 已刷入与实机验证

- 用户明确授权直接刷入 Recovery。r11 和 r12 均只写活动槽 recovery_a；
  Fastboot 发送、写入与 reboot recovery 全部 OKAY。
- r12 镜像：artifacts/recovery-sheng-lineage-24.0-r12-native-source-touch-rotation/
  lineage-24.0-sheng-recovery-r12-native-source-touch-rotation.img
- SHA256：62049d914a2711e0022aa04670812f3f152c58c9e61082fe7e7de62852d78350。
- 实机 ADB uname 确认为 5.15.220-gf9ca2b71f672，variant 为
  r12-native-source-touch-rotation，触摸映射属性自动为 ROTATION_RIGHT。
- Recovery、sheng-recovery-touch 服务为 running；ADB 为 adb，模型初始化成功。
- misc 链接为 /dev/block/by-name/misc -> /dev/block/sda11，Recovery 成功清除 BCB。
  用户已确认原来的 misc 报错消失。
- 实机日志：reports/device/flash-recovery-20261106-065927/。
- 完整 Lineage ZIP 实机运行仍未验证，device-audit.pending 保留。

## 触摸映射的实机证据

- 实际屏幕为横向 3048×2032，NVT 驱动报告竖向范围 X 0..20319、Y 0..30479。
- 用户按屏幕方向划左上→右下和右上→左下两条对角线；原始轨迹分别为
  (20103,37)→(26,30077) 与 (20167,30303)→(14,484)，接近全屏范围。
- 正确映射为屏幕 X=3048×原始Y/30479、屏幕 Y=2032×(1−原始X/20319)。
  使用 Recovery 已有的 ro.minui.default_touch_rotation=ROTATION_RIGHT 完成修正。
- 在 r11 RAM 应用后，用户明确确认“点击位置正确，返回也正常”。
- r12 把同样设置写入根目录硬件 init RC 的 on init；重启后属性自动生效。
- 用户初报 r12 无响应后纠正：触摸启动很慢，大概要十几秒，之后可响应。
  未将“服务 running”单独当作触摸立即可用的证明。
- 坐标采集器使用 EVIOCGRAB 保持 DRM 运行并独占输入，避免菜单误操作。
  首次 stop recovery 导致显示休眠、没有事件的采集已纠正，不作为硬件故障证据。
- 坐标证据：reports/device/flash-r11-20261106-065144/touch-coordinate-analysis.json。

## 冷启动延迟

r12 实机 dmesg 时间：

- 3.7156 秒：nvt_ts_probe 开始；3.7399 秒结束。
- 4.2454 秒：sheng-recovery-touch 启动；4.2509 秒完成设备 mmap。
- 17.9110 秒：开始请求 novatek_nt36532_n81a_fw_csot.bin。
- 18.0079 秒：触摸芯片固件更新成功，更新本身仅约 96.7 毫秒。

主要等待发生在驱动完成 probe 与发起固件更新之间，约 14.17 秒。
因此目前服务已启动不代表芯片已就绪；没有为缩短时间修改原厂模块二进制或
冒险重复触发固件更新。触摸延迟优化尚未实施。
证据：reports/device/flash-recovery-20261106-065927/touch-startup-timing.txt。

## 包校验与先前判断纠正

- 内核 Image 与本项目已导出的源码 boot 内核一致，官方 LOS SM8550 提交
  f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d。
- 336 模块中 zram/zsmalloc 为源码构建，其余 334 为原厂板级模块。
  17045 项导入 CRC 检查通过，未修改 vermagic/CRC。
- AVB、解包后的内核/ramdisk/DTB/DTBO/模块/脚本回读、Windows 导出 SHA 均通过。
- 先前 r8/r9/r10 USB 失败后的旧串口日志仍为 5.15.178 诊断镜像。
  把它误归到源码内核的判断已向用户撤回。物理重新进入 Fastboot 后 r10 临时
  启动成功，r11/r12 ADB uname 才是源码内核运行的直接证据。

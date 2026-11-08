# 蓝牙自动连接默认值的分区归属

2026-11-08，r26 实际启动日志包含 vendor_init 设置
bluetooth.auto_connect_profiles.enabled 时被 bluetooth_prop 策略拒绝。
证据：reports/device/r26-20261108-085804/startup-logcat.txt。

当前固定上游 PhonePolicy 构造函数读取此属性，缺省为 false。
设备树原本意图启用自动连接其它 profile，却把属性放在 vendor.prop，
因此该默认值被拒绝，不能据源文件中的 true 认为已经生效。

把同一个 true 默认值移到 system_ext.prop。init/property_service.cpp 根据
/vendor、/odm 等路径选择 vendor_init 上下文；system_ext 使用平台 init 上下文。
该调整不改变蓝牙公共源码，不扩展 SELinux 规则，也不改音频 offload、编解码
优先级、配对记录或用户选择。当前构建入口已使用 TARGET_SYSTEM_EXT_PROP。

PhonePolicy.java 的属性读取和 mAutoConnectProfilesSupported 分支是行为依据；
system/sepolicy/private/property_contexts 以及 property.te/vendor_init.te 是归属依据。
新增 Bluetooth 仓库到物理上游审计范围。构建、定范围封装、刷入和实际
PhonePolicy 状态必须分别记录。配置修正不能等同于耳机实际自动重连验收。

其它四条蓝牙属性拒绝仍待逐项确认支持状态，不顺手开放权限。
LHDC v5 仍缺实际对端协商证据，不将本项归为 LHDC v5 已修复。

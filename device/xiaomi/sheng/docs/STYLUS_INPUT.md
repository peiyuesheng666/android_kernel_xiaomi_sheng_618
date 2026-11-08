# 手写笔输入方向配置

两种内置笔输入为 NVTCapacitivePenM80p 和 NVTCapacitivePenP81c。
已保存的系统输入记录将它们识别为 TOUCHSCREEN | STYLUS，配置文件为空；
原始 X=0..20319、Y=0..30479，主屏自然方向为 3048x2032 横屏。
原先已修正的手指输入使用相同的原始坐标范围及 ORIENTATION_90，
而两个笔设备仍使用默认 Rotation0，导致方向与手指不一致。

依据：workspace reports/device/system-touch-20261106/input-after-rotation.txt
中的两个 Touch Input Mapper，及
reports/device/20261106-003658/input-diagnostics.txt 的驱动能力枚举。
当前设备树未提供同名笔 IDC，也没有其他 vendor/product 标识规则覆盖它们。

本次仅补两个按设备名匹配的 IDC，并使用标准 PRODUCT_COPY_FILES 安装到
vendor/usr/idc。方向与已验收的手指输入一致：touchScreen、orientationAware=1、
ORIENTATION_90；显式保持设备为内置。未改变压感、倾斜、笔尖/悬浮、按键、
配对、触摸固件、手指配置、屏幕唤醒或任何应用/服务。

框架 TouchInputMapper::parseParameters 接受 ORIENTATION_90；这是现有平台
支持的属性，无需改公共源码。平台 validatekeymaps 已构建并通过两个笔 IDC
以及原有手指 IDC 的 PropertyMap 解析。自动检查只覆盖配置与坐标映射，
不能证明笔的充电/配对、实际落笔/悬浮或快捷键已经正常。

r25 镜像已封存，本次笔配置不在 r25 中。目标 ca10ede3 当前没有 ADB，
笔方向配置尚未刷入；手写笔整体仍列待修，等待下一批其他独立问题和实机验证。

## 构建边界与主机限制

正式产品构建尚未完成：第一次 WSL 发行版重启，未观察到构建结束；第二次
因 C 盘剩余空间降至约 286 MB，主动终止依赖图分析。停止后空间回升至约
4 GB。后续单独构建检查工具时，同样在 326/329 步停止完整图，避免写满 C 盘。

build_sheng_input_validator.py 从实际生成图原样提取最后的 Rust 静态归档及
链接规则、模块参数和原始命名依赖声明，生成小图完成剩余动作；不改公共
源码或编译参数，不以伪造 phony 声明掩盖缺失输入。随后运行当前平台真实的
validatekeymaps，三个配置解析通过。这不能记为完整产品或安装文件构建通过。
证据与精确命令在 workspace reports/device/pen-config-validation-20261108。

新工具、配置及离屏视频诊断后的公共源码审计仍按既定流程保存。
主机低空间问题解决前，不反复启动完整 Soong 图分析。申请把原始报告移入
现有 E 盘产物目录的操作被自动审批以“blocked by policy”拒绝，未执行迁移；
既有文件位置保持原样。本轮只清理了独立确认的失败 r25 封装临时目录，
其日志、元数据和文件哈希已保留，正式 r25 发布产物未改。

参考树中另有笔的黑屏唤醒及配套应用，但不能仅凭名字直接移植到本机。
本机原厂 Vendor_0022_Product_5081.idc 与抑制 BUTTON_7..10 字符的 KCM
已经在 proprietary-files、生成的 vendor mk 及当前 system_ext 安装输出中，
不重复添加，也不把已有功能计为本次修复。P81c 的 ABS_BRAKE 与 BTN_JOYSTICK
被平台同时识别为 joystick；其原厂私有语义尚未确定，不猜测重映射成笔快捷键。

## r28 已安装状态（2026-11-08）

r28 已在 ca10ede3/b 刷入，两份 IDC 的安装哈希通过，dumpsys input 实际加载
对应 vendor/usr/idc 文件，两种笔的 mapper 均为 Rotation90。七分区回读及
新增 crash buffer 检查通过。当前不再是“尚未刷入”；上文为此前构建历史。

实际落笔、悬浮、压感、充电/配对和按键仍未验收。正在参考用户指定的 piano
设备树及其配套模块；不执行其 vendorsetup，不应用公共 framework 或 SystemUI
补丁。其 Xiaomi TouchFeature AIDL 服务在本机未注册，必须先匹配 sheng 接口，
不能直接安装依赖阻塞等待该服务的应用并声称完整适配。

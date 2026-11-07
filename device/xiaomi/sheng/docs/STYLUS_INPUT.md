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
支持的属性，无需改公共源码。正在构建正式安装文件和平台 validatekeymaps，
将使用当前平台的 PropertyMap 解析它们。自动检查只覆盖配置与坐标映射，
不能证明笔的充电/配对、实际落笔/悬浮或快捷键已经正常。

r25 镜像已封存，本次笔配置不在 r25 中。目标 ca10ede3 当前没有 ADB，
笔方向配置尚未刷入；手写笔整体仍列待修，等待下一批其他独立问题和实机验证。

参考树中另有笔的黑屏唤醒及配套应用，但不能仅凭名字直接移植到本机。
本机原厂 Vendor_0022_Product_5081.idc 与抑制 BUTTON_7..10 字符的 KCM
已经在 proprietary-files、生成的 vendor mk 及当前 system_ext 安装输出中，
不重复添加，也不把已有功能计为本次修复。P81c 的 ABS_BRAKE 与 BTN_JOYSTICK
被平台同时识别为 joystick；其原厂私有语义尚未确定，不猜测重映射成笔快捷键。

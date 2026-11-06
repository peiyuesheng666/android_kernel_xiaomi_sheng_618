# sheng 设备配置复查

**2026-11-05架构更新：**本报告下文保留上一轮硬件复查记录。
当前已经改为独立设备树，构建/运行/提取均不再引用sm8550-common；
板级配置、平台HAL选择及必要辅助源文件在sheng本树维护，私有文件统一2027项。
当前结构与验证范围以 `device/xiaomi/sheng/README.md`、
`standalone-checks.json`、`standalone-migration.json` 为准。

这份报告描述编译前配置覆盖范围，不是开机认证。此前仅用脚本/文件存在检查就称
“编译准备完成”，表述过早；完整 Soong/Kati 配置求值、内核ABI和镜像验证仍待源码同步后进行。

## 产品身份

| 字段 | 当前值 | 依据 |
|---|---|---|
| PRODUCT_MODEL | 24018RPACC | 用户所给国行包 odm/etc/build.prop 的 ro.product.odm.model |
| PRODUCT_DEVICE / OTA assert | sheng | 同文件 ro.product.odm.device、原厂产品包标识 |
| PRODUCT_NAME | lineage_sheng | 自建 LineageOS 产品入口，非硬件型号 |
| PRODUCT_MARKETNAME | Xiaomi Pad 6S Pro 12.4 | 原厂 ro.product.odm.marketname |
| SoC/platform | SM8550 / kalama | 原厂DTB和官方平台源码 |
| N81A | 原厂板级标识/固件文件名 | 不能替代产品代号sheng |

国际版型号24018RPACG见[小米官方说明书](https://gl123.alsgp0.mi-fds.com/gl123/XiaomiPad/Xiaomi%20Pad%206S%20Pro%2012.4/N81A_PAD_QSG_en%20hk%20ar_A_V5.pdf)。
本次配置使用用户国行固件的24018RPACC，不以商品名称替代型号代码。

## 与 piano 的覆盖范围比较

piano 当前参考分支是独立SM8750/6.6配置；本工程使用官方SM8550公共配置、内核和模块源。
因此文件数量不可直接比较，必须把继承的实现算入。以下同时列出真实缺口和已修正项。

| 子系统 | 当前来源/实现 | 验证情况 |
|---|---|---|
| 架构、HAL平台、启动头、USB、Wi-Fi/BT、OTA/AVB | LineageOS官方sm8550-common、hardware/xiaomi和qcom-caf；本树覆盖sheng差异 | 待完整构建及实机 |
| boot/init_boot/vendor_boot/recovery/dtbo/super布局 | 原厂镜像及liblp校验，覆写手机分区容量 | 元数据已核对；待最终镜像尺寸验证 |
| fstab和早期挂载 | 官方5.15公共fstab适配sheng，单独fstab.sheng模块，vendor ramdisk及recovery引用 | 路径已配置；挂载/加密须实机验证 |
| 内核与通用/高通模块 | 官方LineageOS SM8550 5.15源码；独立sheng配置片段 | 源码依赖同步中；尚未编译 |
| 板级模块 | 原厂FPC/Novatek/Nanosic/Cirrus/充电等17个模块，含3个依赖模块 | 已提取；真实导入符号与CRC检查在编译阶段执行 |
| hwid产品识别 | 官方hwid.c的SOC_207_PRODUCTS已包含sheng | 已阅读固定提交的源码，不需要假装成fuxi |
| 触摸与recovery | N81A专用2份bin+1份ini，主系统ODM、vendor ramdisk及recovery均配置输入 | 已检查文件，待驱动加载测试 |
| 手写笔/键盘/指纹输入 | 原厂system_ext的kl/idc/kcm及uinput-fpc配置 | 已提取并纳入生成清单；手势体验待实机 |
| 侧边指纹 | FPC HAL、type=side、独立init权限和SELinux | 源码/原厂路径已核对；不标记为已工作 |
| 音频 | 原厂mixer/resource manager/card-defs/microphone布局及Forte ACDB | 替代手机通用声卡/麦克风配置；待音频HAL验证 |
| 显示/电池overlay | 从原厂APK解出的亮度曲线、默认亮度、144Hz默认值及10000mAh power_profile | aapt2资源编译通过；完整RRO链接/效果待验证 |
| 温控、摄像头、固件 | 原厂vendor/odm全量提取物、专有文件清单、官方公共实现 | 提取成功；HAL ELF接口/运行行为待构建和实机 |
| SIM、NFC控制器、GNSS、IR声明 | 清理公共手机配置中与本固件服务不匹配的声明/包/属性 | 不据此否定官方规格中被动NFC标签功能 |
| PixelOS/Evolution X入口 | 尚未接入 | 首轮先完成LineageOS，不能用未验证入口冒充多ROM支持 |

## 本次实际修复

- 型号从商品名改为24018RPACC，代号保留sheng。
- 修正生成器的章节识别：原先遗漏小写开头的eUICC，且未清除GNSS/IR等权限声明。
- 移除手机telephony/carrier overlay与RIL/IMS属性，覆盖SIM物理槽位为0。
- 增加xiaomifp和xiaomi_wifi_gpio原厂模块，准备模块总数17。
- 增加独立fstab、recovery/早期触摸固件、手写笔idc/kcm及FPC输入配置。
- 从原厂资源重新解出亮度与电池模型，读取原厂声卡及麦克风配置。

## 私有文件缓存

缓存目录：`/root/sheng-lineage/firmware-dump/`（C盘WSL）。

- vendor、odm、vendor_dlkm、system_dlkm及系统分区已解包到partitions。
- hardware内保存27个启动/固件镜像，来源映射以原厂flash_all.bat的内容为依据；未执行刷机脚本。
- 640个模块文件条目：vendor_boot 336、vendor_dlkm 304、system_dlkm 0，存在跨分区重复。
- DSP/modem/蓝牙文件系统已从C盘缓存副本只读挂载并提取。
- 5241条vendor/odm/dlkm文件及链接清单已记录SHA256/目标。
- 完整索引：hardware/stock-hardware-inventory.json；摘要：stock-hardware-cache.json。
- 原厂包只读，构建准备已改为从C盘缓存取DT/固件，不依赖向原包写入。

## 仍不可声称开机的原因

必须先验证5.15.211源码内核与原厂私有模块的CRC、导出符号、保护符号和接口。
随后必须通过完整Android构建、VINTF/ELF/SELinux检查及用户的实际设备启动日志。
17个ko已提取和安装器测试通过，不能替代这些验证。此结论不受piano目录文件数量影响。

官方屏幕/电池规格核对来源：[小米规格页](https://www.mi.com/global/product/xiaomi-pad-6s-pro-124/specs/)。

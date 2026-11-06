# piano 参考项目核对

仅阅读其组织方式；没有复制该项目的源码、驱动、模块、设备树或预编译内核。

- 设备配置：<https://github.com/xiaomi-pad-8-pro-development/android_device_xiaomi_piano>
- 唯一公开分支（本次核对）：`seventeen`。
- 该分支 README 的产品入口包含 LineageOS / Evolution X 的 `lineage_piano`
  及 PixelOS 的 `custom_piano`。这是 Android 产品构建层的入口，与内核版本迁移是两项工作。
- `BoardConfig.mk` 当前为 `TARGET_KERNEL_VERSION := 6.6`，并引用独立的内核产物仓库。
- 内核源码仓库的 `seventeen/README.md` 同样明确写 Linux 6.6。
- 因此当前默认分支不能作为 piano 已完成 6.12 迁移的证据。

## sheng 官方固件已经确认的事实

输入为用户提供的 OS3.0.303.0.WNXCNXM Android 16 线刷包。
解析结果和输入镜像哈希见 `stock-boot.json`、`stock-ramdisk.json`。

- `boot.img` 为 header v4，内核为未压缩 ARM64 Image。
- 内核 banner：`5.15.178-android13-8-00021-g6f2f96be86b9-ab13729987`。
- `init_boot.img` 独立承载通用 ramdisk。
- `vendor_boot.img` 承载厂商 ramdisk、模块和拼接的基础 DTB。
- 厂商 ramdisk 有 336 个 `.ko` 文件条目，并含 `modules.load`、依赖和 blocklist。
- 基础 DTB 共 8 份，根 compatible 为 `qcom,kalama` 或 `qcom,kalamap`。
- 原版 vendor 模块不能直接用于跨 LTS 的 6.12 内核。

当前交付阶段只构建 ACK 内核，不同步 Android 系统源码；启动镜像重打包和硬件启动测试尚未进行。

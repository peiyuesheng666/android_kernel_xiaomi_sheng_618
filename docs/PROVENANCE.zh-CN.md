# 源码来源与构建

Linux 基础为 ACK 6.18.32，固定提交 ff4a6c3bb0f471a9dd186293a47b62c83829b97d。
SM8550 参考适配来自 JiaqiLi404/android_kernel_618_for_sm8550，固定提交 c3956156ce7c4193c451dfda531fad72d35bfebb。
MiCode、LineageOS 和 Droidspaces 的来源与固定提交保存在 provenance/。

Qualcomm WALT 来自 CodeLinaro kernel.lnx.6.12.r70-rel，固定提交 46f13428ae2d6e32ddfe2f3e5cb5046428ae73b4。
本版源码与镜像记录见[WALT 来源记录](../provenance/walt-charge-release.json)。

工程使用已适配的固定源码快照 sheng-kernel-build-inputs.tar.gz。
构建入口读取固定源码、修正路径并回放适配补丁，生成外部 BUILD_ROOT 中的源码树。
完整源码包已包含该输入；归档内部的名称用于解包和来源追溯。

kernel/ 中保留驱动审核副本，实际构建使用 BUILD_ROOT 中的源码。
构建步骤见[构建说明](BUILD.zh-CN.md)，原始开发记录见[历史说明](HISTORY.md)。
原有 SPDX 标识和许可证文件保留。

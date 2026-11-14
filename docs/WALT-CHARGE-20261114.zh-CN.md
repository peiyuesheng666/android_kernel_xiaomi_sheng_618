# 小米平板 6S Pro WALT 内核 · 20261114

- 补回 Qualcomm WALT 调度和 CPU 调速。
- 保留手写笔修复，补齐必要温控和充电接口。
- 修复 CPU 深度空闲兼容问题。

已刷入 HyperOS OS4.0.2.0.XPYCNXM，并用同一酷泰科充电宝熄屏复测约十分钟。
功率平缓下降，用户反馈充电宝显示最低约 60W。实测使用平板现有的系统温控配置。

源码回放、模块 ABI/BTF、boot 和 AVB 完整性校验通过。
发布文件包含 Image、boot.img、完整源码和 SHA256SUMS，构建步骤见[构建说明](BUILD.zh-CN.md)。

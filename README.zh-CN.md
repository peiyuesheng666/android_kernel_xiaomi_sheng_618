# 小米平板 6S Pro 内核

Linux 6.18.32，适配小米平板 6S Pro（sheng，骁龙 8 Gen 2）。
编译和实机验证使用 HyperOS OS4.0.2.0.XPYCNXM。

[English](README.md) · [下载当前版](https://github.com/peiyuesheng666/android_kernel_xiaomi_sheng_618/releases/latest) · [构建步骤](docs/BUILD.zh-CN.md)

## 已完成改动

- 补回 Qualcomm WALT 调度和 CPU 调速。
- 整合手写笔修复，恢复原厂手写笔充电状态接口。
- 补齐必要的温控和充电接口。
- 修复 CPU 深度空闲兼容问题。

已刷入平板并用同一酷泰科充电宝熄屏复测约十分钟，功率平缓下降；用户反馈充电宝显示最低约 60W。
实测使用平板现有的系统温控配置。源码回放、模块 ABI/BTF、boot 和 AVB 校验通过。

## 下载文件

| 文件 | 内容 |
| --- | --- |
| Image | 已内嵌模块的内核镜像 |
| boot.img | 完整启动镜像 |
| sheng-kernel-source.tar.gz | 构建项目与完整固定源码输入 |
| SHA256SUMS | 发布文件校验值 |

发布页还提供项目 ZIP、单独的构建输入和 Git 历史备份。
工具链、匹配的原厂 boot 模板和编译命令见[构建步骤](docs/BUILD.zh-CN.md)。

[功能说明](docs/FEATURES.zh-CN.md) · [源码来源](docs/PROVENANCE.zh-CN.md) · [检查入口](docs/VALIDATION.zh-CN.md) · [提交历史说明](docs/HISTORY.md)

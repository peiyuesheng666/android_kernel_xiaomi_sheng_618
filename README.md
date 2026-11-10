# 小米平板 6S Pro · Linux 6.18.32

当前内核项目按 [小米 13 Pro 参考仓库](https://github.com/JiaqiLi404/android_kernel_618_for_sm8550)
的结构整理。设备代号 sheng，目标系统 HyperOS OS3.0.303.0.WNXCNXM。
早期 6.12 基线已退役并删除。

## 源码与构建

- [内核工程说明](kernel-project/README.zh-CN.md)
- [Bash 构建入口](kernel-project/build.sh)
- [构建与依赖](kernel-project/docs/BUILD.zh-CN.md)
- [来源与目录布局](kernel-project/docs/PROVENANCE.zh-CN.md)
- [验证说明](kernel-project/docs/VALIDATION.zh-CN.md)

WSL Ubuntu-22.04：

```text
/root/sheng-618-project                         整理后的项目
/root/sheng-618-project-build/k618/ws/common     ACK 6.18 主源码
/root/sheng-618-project-build/k618/soc           SoC 外部驱动
/root/sheng-618-project-build/k618/vendor        厂商外部驱动
/root/sheng-618-project-build/k618/sheng-ports    平板专用驱动
/root/sheng-618-project-deps                     本次验证使用的独立工具链
/root/sheng-source-inputs                       共用原厂解析与参考输入
```

```bash
cd /root/sheng-618-project
bash scripts/run-limited.sh bootstrap
export PREBUILTS=/root/sheng-618-project-deps/prebuilts
export ELFUTILS=/root/sheng-618-project-deps/elfutils-0.193
bash build.sh
bash scripts/run-limited.sh verify
```

最终文件在项目的 `dist/release-r70/`。模块采用与参考项目相同的外部编译机制，
生成 `/lib/modules` 模块层并嵌入 Image；完整 ACK 源码没有与厂商驱动强行合并。

## 测试记录

- [r70 原始发布与源码包记录](reports/kernel618-release-r70.md)
- [本次目录整理记录](reports/kernel618-reference-layout.json)
- [6.12 清理记录](reports/kernel612-cleanup.json)

原始 r70 已实机启动。本次整理后重编、刷写和硬件测试结果以新报告为准。
现有 Android 设备配置另见 [sheng 设备说明](device/xiaomi/sheng/README.md)。

# 小米平板 6S Pro 内核

适配 sheng / SM8550，开发验证系统为 HyperOS OS3.0.303.0.WNXCNXM。
默认 release，344 个模块内嵌 Image，关闭 rawdump 与 300 秒回 fastboot。
包含双电池认证、57 个原厂充电节点、旁路供电、第三方 PPS 自动认证与清零恢复、
容器网络/IPv6 NAT、SoC/Scene 识别、手写笔充电接口与 32 ms 滤波、split BTF 构建修复。

## 下载选择

- 使用现有内核镜像：`boot.img`、`Image`。
- 离线获取完整构建源码：`sheng-kernel-source.tar.gz`，已包含固定源码输入。
- Git 克隆或项目 ZIP：另下载 `sheng-kernel-build-inputs.tar.gz` 到项目的 `assets/`。
- 历史：`sheng-port-history.bundle` 保存 427 条原开发提交。
- 说明与校验：`FEATURES.zh-CN.md`、`SHA256SUMS`。

源码依赖统一命名为 sheng-kernel-build-inputs；无需恢复已删除的旧版本工程。
2026-11-12 更新中英文首页、构建与来源说明，并同步项目包和校验清单；
固定源码输入、boot.img 和 Image 字节保持不变，没有新增内核编译或刷写。

充电动画与协议能力不等于实际输入功率；长期手写笔/休眠、全部充电器和硬件覆盖
仍需验收，详见功能说明。风驰和 Linux 7.2 zram/swap 未包含在内核中。
工具链、原厂 boot 模板、个人分区备份和独立 /data 温控配置不随源码包交付。
仓库保持私有，原提交历史与 port-history 分支保留；测试结果留在本地。

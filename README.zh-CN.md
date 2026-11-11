# 小米平板 6S Pro（sheng）Linux 6.18.32 · r87

当前版本：**repair-r87**。默认 release，内置 344 个重新编译的模块。

本版本包括双电池认证、Droidspaces/SYSVIPC 与容器网络、IPv6 NAT、SoC/Scene
识别、手写笔充电接口、57 个原厂充电节点、旁路供电、第三方 PPS 自动认证、
以及模块 split BTF 的缓存重链接修复。保留原有 32 ms 手写笔滤波。

- [构建步骤](docs/BUILD.zh-CN.md)
- [功能与实机验证边界](docs/FEATURES-REPAIR-r87.zh-CN.md)
- [源码来源](docs/PROVENANCE.zh-CN.md)
- [验证方法](docs/VALIDATION.zh-CN.md)
- [提交历史](docs/HISTORY.md)

Git 仓库保存构建脚本、配置、补丁和来源记录；完整内核源码通过本仓库
`repair-r87` Release 提供。克隆仓库后下载固定基线缓存到 `assets/`。
完整源码包 `sheng-6.18.32-repair-r87-source-with-inputs.tar.gz` 已包含该缓存。
基线缓存名称沿用 r71，应用补丁后得到 r87；并非在构建旧版本。
不依赖已删除的独立 r76 或风驰工程。7.2 zram/swap 移植未应用到本版本。

`boot.img` 与 `Image` 是现有已验证 r87 产物，本次整理没有重新编译或刷写。
固件能力/充电动画显示 90 W、120 W不等于实际输入达到该功率。
手写笔长期稳定性、所有充电器覆盖及全部硬件功能仍有未完成验收项。

本机曾应用独立 `/data/vendor/thermal/config/thermal-normal.conf` 覆盖；它不在
内核镜像或源码包中，单刷 boot 不会撤销该配置。不能将它当作内核性能改动。

新的功能提交统一归属 GitHub 账号 peiyuesheng666。原 r70 的两条提交保留；
427 条原始共享项目历史在独立 `port-history` 分支，包含内核与设备树开发。
主分支当前文件只用于 r87 内核构建。旧 r70 Release 和标签在 r87 验证后删除。

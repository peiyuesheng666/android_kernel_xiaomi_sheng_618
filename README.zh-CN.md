# 小米平板 6S Pro 内核

[English](README.md) · [构建步骤](docs/BUILD.zh-CN.md) ·
[功能说明](docs/FEATURES.zh-CN.md) · [源码来源](docs/PROVENANCE.zh-CN.md) ·
[检查入口](docs/VALIDATION.zh-CN.md) · [提交历史](docs/HISTORY.md)

下载：**[当前内核](https://github.com/peiyuesheng666/android_kernel_xiaomi_sheng_618/releases/latest)**。
适配设备为 **小米平板 6S Pro**，代号 `sheng`，平台为骁龙 8 Gen 2 / SM8550；
开发与实机验证使用 **HyperOS OS4.0.2.0.XPYCNXM**。
内核为 **Linux 6.18.32**，默认使用 release 配置，**345 个模块内嵌到 Image**。
其他设备或系统版本需要另行验证兼容性。

## 已包含的功能

| 功能 | 当前实现 |
| --- | --- |
| 双电池认证 | 恢复 batterysecret 对真实固件属性 165 的读写 |
| 原厂充电接口 | 补齐 57 个 class 节点：旁路 1 个、标量 51 个、特殊接口 5 个 |
| 旁路供电 | `charging_suspend_battery` 使用固件属性 219，与 `input_suspend` 独立 |
| 第三方 PPS | 满足识别条件后立即自动认证；系统写 0 后即时重判恢复；原装充电器认证优先 |
| 容器支持 | SYSVIPC、IPC/PID/user namespaces、消息队列、devtmpfs 与容器网络配置 |
| 网络与文件系统 | IPVLAN/MACVLAN/VXLAN、VLAN/bridge、overlay，以及内置 IPv6 NAT/MASQUERADE |
| SoC / Scene | SoC ID 536 映射 KALAMAP，恢复平台识别 |
| 手写笔 | 原厂充电 sysfs 与 uevent 字段；保留原有 32 ms 滤波 |
| WALT | 补回完整 Qualcomm WALT，原厂启动脚本自动选择 walt，三个 CPU 策略自动降频 |
| 温控与空闲 | 保留必要的原厂温控消息接口，8 个 CPU 均验证进入 C4 |
| release 行为 | 默认关闭 rawdump 和 300 秒自动回 fastboot |
| 模块构建 | 重新链接 345 个模块，修复缓存模块的 split BTF 问题 |

属性编号、PPS 识别保护和特殊接口格式见 [功能说明](docs/FEATURES.zh-CN.md)。

## 下载哪个文件

全部当前交付文件在 **[repair-当前内核 Release](https://github.com/peiyuesheng666/android_kernel_xiaomi_sheng_618/releases/latest)**。
当前 Release 同时提供镜像、源码和固定构建输入。

| 文件 | 用途 |
| --- | --- |
| `boot.img` | 内核启动镜像，192 MiB，boot header v4 |
| `Image` | 已内嵌模块层的内核镜像 |
| `sheng-kernel-source.tar.gz` | 完整构建项目与固定源码输入，离线获取源码推荐下载此包 |
| `sheng-kernel-project.zip` | 构建项目，未包含大体积源码输入，需要另下载下面的依赖包 |
| `sheng-kernel-build-inputs.tar.gz` | Git 克隆和项目 ZIP 所需的固定 ACK / SoC / techpack / 平板驱动源码输入 |
| `sheng-port-history.bundle` | 427 条原始开发提交的离线历史 |
| `FEATURES.zh-CN.md`、`SHA256SUMS` | 功能说明与发布文件校验值 |

构建输入统一使用统一的依赖包名称。构建入口会校验固定源码输入，修正路径，
按记录回放补丁得到内核源码。完整源码包已包含依赖，无需重复下载；
不需要恢复任何已删除的旧版本工程。工具链和原厂 boot 模板需要单独准备。

## 从源码构建

在 Linux / WSL 的原生 Linux 文件系统内放置工程；`BUILD_ROOT` 必须位于项目外，
路径不得含空格。准备依赖、固定工具链和匹配的原厂 boot 模板后执行：

```bash
export BUILD_ROOT="$HOME/sheng-kernel-build"
export PREBUILTS=/path/to/pinned-prebuilts
export ELFUTILS=/path/to/elfutils-0.193
export STOCK_BOOT=/path/to/sheng-stock-boot.img
export SHENG_BUILD_MODE=release TAG=kernel
bash buildkernel.sh
bash buildmodules.sh
bash embed.sh
bash mkbootimage.sh
bash scripts/run-limited.sh verify
```

产物位于 `dist/kernel/`。`bash build.sh` 可一次运行四阶段。
环境安装、下载命令、工具链布局、原厂模板 SHA256 与配置检查入口见
[构建步骤](docs/BUILD.zh-CN.md)。这些构建入口不会刷写设备。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `scripts/` | 源码准备、路径修正、补丁回放、构建与检查 |
| `sheng_defconfig`、`profiles/` | 内核配置、模块映射和默认构建参数 |
| `patches/`、`provenance/` | 适配补丁、固定上游提交和逐文件哈希 |
| `kernel/` | 平板驱动、充电源码审核副本等 |
| `assets/` | 固定源码输入的本地放置位置及校验清单 |
| `docs/` | 构建、功能、来源、检查和历史说明 |
| `port-scripts/` | 历史开发过程脚本，包含旧绝对路径与设备操作，构建不依赖它们 |

完整 ACK / SoC / techpack 源码由 Release 交付，准备后位于外部 `BUILD_ROOT/k618/`。
充电审核副本的修改不会自动改变外部构建输入，需要同步补丁与来源记录。

## 验证范围与注意事项

当前下载为已刷入验证的 WALT 内核，保留手写笔 v4、温控／充电接口和 CPU 深度空闲修复。
源码哈希、补丁回放、模块 ABI / BTF 与主机充电故障测试的入口见
[检查说明](docs/VALIDATION.zh-CN.md)，测试结果保存在本地 `dist/`。

充电动画显示 90 W / 120 W、协议能力或节点齐全，不等于实际输入功率和全部硬件验收。
手写笔长期稳定性与休眠恢复、低电量峰值、全部充电器及相机/音频/蓝牙等完整覆盖仍待验收。
身份不明且能力 ≥100 W 的第三方 PPS 可能被原装保护策略保守跳过。
风驰已取消；Linux 7.2 zram/swap 移植未包含在内核中。

独立 `/data/vendor/thermal/config/thermal-normal.conf` 温控覆盖不在内核镜像或源码包中，
单刷 boot 不会撤销已有的 `/data` 覆盖。原始提交保留在 Git 历史；
`port-history` 分支保存原共享项目的内核与设备树开发记录。

本版变更、来源及充电复测见 [WALT 发布说明](docs/WALT-CHARGE-20261114.zh-CN.md)。

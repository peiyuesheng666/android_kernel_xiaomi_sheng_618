# 小米平板 6S Pro · Linux 6.18.32

按 JiaqiLi404/android_kernel_618_for_sm8550 的项目布局整理的 sheng 内核构建工程。
目标系统为 HyperOS OS3.0.303.0.WNXCNXM，源码快照对应 release-r70。

这个仓库与小米 13 Pro 参考项目一样，将构建脚本、设备配置、补丁和来源记录放在
项目目录，将内核源码、外部驱动源码和编译输出放在独立的 Linux 构建目录。

```text
sheng-618-project/
├── build.sh                  Bash 构建入口
├── kernel-6.18/              内核构建环境、平板驱动源码和模块表
├── scripts/                  bootstrap / prepare / build / verify
├── profiles/                 r70 配置、techpack 参数、模块加载清单
├── patches/                  已应用适配补丁的审核副本
├── provenance/               固定版本、源码哈希、参考项目与实机记录
├── tools/                    模块加载器、mkbootimg、avbtool
├── docs/                     构建、来源和验证说明
├── assets/                   已校验的完整适配源码缓存；Git 忽略大文件
├── logs/                     构建日志；Git 忽略
└── dist/release-r70/          Image、可选 boot.img 与验证报告；Git 忽略

~/sheng-618-project-build/k618/
├── ws/common/                标准 ACK 内核源码，含 Makefile/arch/drivers/fs/include
├── soc/                      SM8550 SoC 外部驱动
├── vendor/qcom/opensource/   显示、相机、音频、GPU、Wi-Fi 等外部驱动
├── vendor/xiaomi/            适配的旧版 DSP RPC
├── vendor/nxp/、vendor/st/   NFC 等厂商源码
├── sheng-ports/              触摸、键盘、霍尔、指纹、功放、POGO、PS5169
├── mark/                     模块批量加载器
└── out-gki/                  编译输出、模块层和 Image
```

首先按 [构建说明](docs/BUILD.zh-CN.md) 准备固定工具链与 elfutils，然后运行：

```bash
bash scripts/run-limited.sh bootstrap
bash build.sh
bash scripts/run-limited.sh verify
```

构建内核与外部模块的全部步骤均由 Bash 执行。Python 用于源码缓存与哈希检查、
cgroup 限制，以及上游 mkbootimg/avbtool 工具，不负责内核编译调度。
默认限制为 4 个编译任务、12 GiB 内存、1 GiB swap。

源码缓存包含全部适配后的源文件，准备过程不依赖旧工程目录。bootstrap 在本版本
使用随包提供的源码快照；它不会从原始上游自动重演全部历史移植步骤。
补丁保留供审核，缓存中已应用的补丁不能重复应用。

保留 r70 的显示优先加载、键盘、手写笔、USB 和充电适配。测试日志和内置
KernelSU/SUSFS 关闭。正常内核错误信息及 GKI 必需的 ABI/BTF 配置保留。

原始 r70 已实机启动。整理后的工程是否完整重编和实机验证，以
`dist/release-r70/validation.json` 和新的测试记录为准。

参考仓库：https://github.com/JiaqiLi404/android_kernel_618_for_sm8550

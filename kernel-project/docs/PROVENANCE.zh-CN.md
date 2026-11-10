# 来源与整理方式

参考项目固定在 `c3956156ce7c4193c451dfda531fad72d35bfebb`。
其 Git 仓库不包含一棵合并的 Linux 内核源码树，而是构建脚本、补丁、配置和
来源记录。完整 ACK、SoC 和 techpack 源码准备到外部 BUILD_ROOT。

本项目保留同样的边界：`ws/common` 是 ACK；`soc` 是外部 SoC 驱动；
`vendor/qcom/opensource` 等是外部厂商驱动。平板额外驱动放在 `sheng-ports`。
编译后的 `.ko` 汇总成 `/lib/modules` 模块层并嵌入 Image。

`provenance/source-plan.json` 记录 ACK、参考项目、LineageOS 与官方 MiCode
sheng 基础源码的固定版本。`reference-input-sources.json` 保留参考项目的
上游来源记录，仅供审核；其中手机固件、KernelSU 等不是本平板版本的构建输入。

`provenance/source-files.json` 记录实际平板适配源码的逐文件 SHA256。
`provenance/source-cache.json` 记录随包源码缓存的 SHA256。cache 是已应用
所有 r70 适配的完整快照，bootstrap 解压并逐文件检查；补丁副本用于审核。
这版未实现从各原始上游仓库重演全部历史修改的网络 bootstrap。

`provenance/relocations.json` 记录 PS5169 Makefile 的路径修正：将旧工程的
绝对头文件路径改为 `$(SOC)/include`。bootstrap 在哈希核对前执行该修正，
其余适配源码保持快照内容。

`kernel-6.18/sheng-ports` 保留平板专用驱动的审核副本，构建使用准备后的
`BUILD_ROOT/k618/sheng-ports`。`kernel-6.18/modules.tsv` 给出所有模块的源码路径。
所有上游许可文件、SPDX 标识和源码头保持原样。

# sheng 6.18 移植：来源和 ABI 核查

2026-11-08。主要目标为当前 LineageOS 24.0，保留原厂 HyperOS 兼容方向；
两个系统都需要分别通过实际启动和硬件验证。当前已编译 6.18.32 开发基线和
LOS kalama TCSR 驱动，尚无完成板级适配的 sheng 内核、boot 镜像或可刷包。

## 选定来源

2026-11-08 用户最新确认：SM8550 驱动以 LOS 官方三仓库为主，缺失的平板驱动
允许补用小米官方 sheng 源码。LOS 版本与当前 ROM 已审计的输入一致；没有改动现用
ROM 的公共源码、BoardConfig、模块选择或任何设备分区。

| 仓库 | 固定提交 |
| --- | --- |
| [LOS kernel](https://github.com/LineageOS/android_kernel_xiaomi_sm8550) | `f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d` |
| [LOS modules](https://github.com/LineageOS/android_kernel_xiaomi_sm8550-modules) | `92a9fde479d3262da080cfd28bab0775b0da500a` |
| [LOS devicetrees](https://github.com/LineageOS/android_kernel_xiaomi_sm8550-devicetrees) | `43b5ada5654ed84c25f74789bc8f6326b7bacd20` |

LOS 内核输入仍是 5.15。6.18 核心参考 ACK
`ff4a6c3bb0f471a9dd186293a47b62c83829b97d` / 6.18.32；需要将 LOS 的相关驱动和
接口迁移到该核心，不能通过修改 Makefile 版本号得到 6.18。

[13 Pro 参考项目](https://github.com/JiaqiLi404/android_kernel_618_for_sm8550)
固定在 `c3956156ce7c4193c451dfda531fad72d35bfebb`。它用于研究移植与打包方法；
不能直接使用 nuwa 的启动镜像、手机触摸配置或面板参数。参考项目自己的 README
仍标注真机验证待完成。

本项目的输入选择在
`device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json`。
三个 LOS 仓库已经完整检出在 `/root/sheng-618/src/lineage-*`。官方 sheng 补充
来源固定在同一 source-plan 的 `supplemental_board_sources`，内核、音频和两份
设备树已经完整检出；显示和相机驱动暂为目录索引。固定提交、树 ID、实际检出
状态和文件名覆盖见 `kernel618-source-audit.json`。

## 2026-11-08 实际构建与首个驱动移植

- ACK 核心保持固定提交且工作区干净；24 线程编译成功，版本为
  `6.18.32-4k-android17-5-sheng-ack-baseline`。输出在
  `/root/sheng-618/out/ack-dist`，包括 Image、Image.gz 和 105 个配套 GKI 模块。
- Ubuntu 的 elfutils 0.186 无法解析 Clang 生成的 Rust helper DWARF5 行表；
  仅禁用 ZSTD 压缩也不能解决。新增私有 elfutils 0.193 准备脚本，固定归档 SHA256，
  不替换系统库；确认 gendwarfksyms 实际加载私有 libdw/libelf。保留 Rust、BTF、
  MODVERSIONS 和 GENDWARFKSYMS。
- 实际复用 ROM 的 Clang r584948b 和 Rust 1.91.1，与 ACK 推荐的 r584948c /
  1.91.1.p3 不同。记录实际版本和哈希，不宣称兼容 madrid 二进制或其 KMI。
- 从固定 LOS 内核移植 `tcsrcc-kalama.c`，保留六路时钟的编号、寄存器和
  `qcom,kalama-tcsrcc` 绑定。使用未修改的 ACK 公共时钟代码生成 clk-qcom.ko，
  单独生成 tcsrcc-kalama.ko；输入源码不修改，每个暂存文件记录来源及哈希。
- TCSR 没有 voltage proxy votes 或 critical clocks，sync_state 改接 ACK 的
  clk_sync_state；保留休眠恢复的 clk_restore_context。ACK 无下游 DEEPSLEEP
  扩展，此路径未实现、未实测，其他控制器的 PLL/电压框架仍待迁移。
- ARM64 Image 头、gzip 回解、分发副本哈希、107 个模块的结构和依赖闭合、
  6,169 项真实导入 CRC、命名空间和依赖排序检查通过，无缺失符号或重复导出。
  基线模块有签名尾部；未做签名密码学验证，两个新移植模块尚未安装或签名。
  完整验证和产物哈希见 `kernel618-build-verification.json`。

## “只换内核、不动模块”的核查

参考项目依赖 `.ko`，并声明统一生成 406 个配套模块：公开驱动重新编译，另外
选用 madrid 官方固件中的 54 个 6.18 模块。它修改 initramfs 解包顺序，把自带的
模块层解包到 bootloader 提交的启动盘之后，覆盖同名模块和加载清单；原有
init/vendor/recovery 启动逻辑仍负责启动。只刷 boot 是交付方式，不能推出运行时
完全沿用原来的 5.15 模块。源码证据的具体行号和哈希见 `kernel618-source-audit.json`。

因此，6.18 适配可研究“只交付一个 boot，但内含匹配的替换模块层”的方式。
是否适用于 sheng 的 init、vendor_dlkm 和 system_dlkm 加载路径，仍需另行验证。
本次没有制作这样的包，也没有绕过 CRC 检查或修改原厂模块。

## 实际模块核查

新增 `scripts/audit_kernel618_modules.py`，逐一验证原厂 BSP 清单中的 417 个模块
SHA256。候选核查另加入候选内核编译的 zram/zsmalloc，合计 419 个有效模块。
检查 basic/extended modversions、真正的符号提供者、重复导出、缺失符号、
`module_layout`、vermagic 标志和 `.gnu.linkonce.this_module` 大小。

| 对照 | 结果 |
| --- | --- |
| 当前 LOS `5.15.220-gf9ca2b71f672` | 25,134 项版本化导入全部匹配；无缺失符号、CRC 或结构大小错误 |
| 已有 ACK `6.12.96-4k-android16-7-sheng-ack-baseline` | 检查 25,216 项；19,002 项 CRC 不同、2,990 项缺失提供者、52 项重复导出；417 个原厂模块结构均为 960 字节，候选模块结构为 1,600 字节 |
| 新 ACK `6.18.32-4k-android17-5-sheng-ack-baseline` | 25,215 项导入；18,636 项 CRC 不同、3,356 项缺失提供者、52 项重复导出；417 个原厂模块结构均不匹配，不能混用 |

5.15 对照还发现三个已解析、但原厂未提供 CRC 的导入（btpower 两项、nxp-nci
一项）。真实加载器允许这些导入；报告列为 warning，不把它们写成“已由 CRC
证明兼容”。静态核查不替代签名、命名空间、设备树绑定、内存语义或硬件测试。

6.12 是用于检验核查工具能拒绝跨版本不匹配输入的真实对照，不是 6.18
的实测结果。6.18 的真实结果单列于 `kernel618-audit-candidate-618.json`；它核查
“基线加原厂模块”的不兼容性，不等同于上面 107 个新编译模块的闭合检查。

结果分别见 `kernel618-stock-inventory.json`、`kernel618-audit-control-515.json`
和 `kernel618-audit-control-612.json`。失败报告保留准确总计和前 80 条示例，
避免将完整重复错误列表纳入 Git。

核查工具还通过五项验证：真实 5.15 模块对照、禁止 5.15 候选冒充 6.18、
删除临时 symvers 副本中的 module_layout 提供者后拒绝全部 419 个模块、
长符号名 extended modversions 解析、截断 CRC 数组拒绝。
结果见 `kernel618-audit-tool-validation.json`；临时副本检查没有修改真实内核
输出或原厂模块。

## 仍需解决的适配

三份固定 LOS 仓库的文件目录检索未找到平板特定的 NT36532、Nanosic 键盘、
霍尔、metis、POGO 充电、CS35L43 和 N81A 面板实现文件。补充官方 sheng 来源后，
已找到 POGO、CS35L43 和面板来源，九仓库的文件名检索仍缺少 NT36532、
Nanosic 键盘、霍尔和 metis。这不代表全网没有公开实现；命中一个 touchfeature
文件也不能证明它兼容平板
的 host-processing/笔协议。当前可用 5.15 方案依赖原厂 BSP 模块，不能据此宣称
LOS 公共源码已经完整重建平板驱动。

下一阶段必须处理 LOS 通用驱动到 6.18 的迁移和这些平板接口，再完成有效模块
闭合、合并 DTB/DTBO 绑定、启动包及 AVB 检查，最后在授权后做实机启动和硬件验证。

C 盘约剩 10.3 GiB。容量工具验证当前注册 VHDX 非 sparse/压缩文件，并计算已
分配块内可复用空间的保守下界；构建前有效预算约 83.8 GiB，包含约 73.5 GiB
已落盘的可复用空间，故 40 GiB 预留检查通过。不能把 WSL 内部约 505 GiB 空闲
全部当成宿主容量。没有清理其他任务的产物或缓存。容量读数见
`kernel618-wsl-space.json`。

## 重跑

```bash
# 获取/复用固定的 LOS Git 目录索引，无完整检出、无编译、无刷机。
python3 scripts/prepare_kernel618_sources.py --catalog-only
python3 scripts/audit_kernel618_sources.py --output reports/kernel618-source-audit.json

# 检查完整构建的预留空间；空间不足返回 2。
python3 scripts/prepare_kernel618_sources.py --preflight

# 编译基线、首个 LOS 控制器，再验证真实产物。没有刷机操作。
bash scripts/build_kernel618_baseline.sh
bash scripts/build_kernel618_clock_port.sh
python3 scripts/verify_kernel618_build.py

# 检查原厂 BSP 原始文件哈希和 ELF 信息；成功只是清单核查成功。
python3 scripts/audit_kernel618_modules.py \
  --stock-root /root/sheng-lineage/firmware-dump/hardware/modules \
  --output reports/kernel618-stock-inventory.json
```

候选检查时再提供 `--kernel-out`、两个 `--gki-module`，默认要求 6.18。
现有 5.15/6.12 对照必须明确设置 `--expect-series`，不会冒充 6.18 结果。

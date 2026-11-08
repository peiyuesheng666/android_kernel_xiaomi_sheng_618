# sheng 6.18 移植：来源和 ABI 核查

2026-11-08。主要目标为当前 LineageOS 24.0，保留原厂 HyperOS 兼容方向；
两个系统都需要分别通过实际启动和硬件验证。当前没有编译完成的 sheng 6.18
内核、boot 镜像或可刷包，本报告不宣称已完成移植。

## 选定来源

按用户最新要求，SM8550 驱动来源采用 LOS 官方三仓库，不使用 MiCode sheng
源码作为构建输入。版本与当前 ROM 已审计的内核/BSP 输入一致；没有改动现用
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
三个 LOS 仓库的 Git 目录已经准备在 `/root/sheng-618/src/lineage-*`，固定提交和
树 ID 见 `kernel618-source-audit.json`。这些是没有完整检出的源码目录索引，
不属于已经构建好的内核。

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
| 新 6.18 候选 | 尚未构建，尚无真实 ABI 检查结果 |

5.15 对照还发现三个已解析、但原厂未提供 CRC 的导入（btpower 两项、nxp-nci
一项）。真实加载器允许这些导入；报告列为 warning，不把它们写成“已由 CRC
证明兼容”。静态核查不替代签名、命名空间、设备树绑定、内存语义或硬件测试。

6.12 是用于检验核查工具能拒绝跨版本不匹配输入的真实对照，不是 6.18
的实测结果。不能把这些数值写成新 6.18 的失败统计。

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
霍尔、metis、POGO 充电、CS35L43 和 N81A 面板实现文件。检索只覆盖所列三库，
不代表全网没有公开实现；命中一个 touchfeature 文件也不能证明它兼容平板
的 host-processing/笔协议。当前可用 5.15 方案依赖原厂 BSP 模块，不能据此宣称
LOS 公共源码已经完整重建平板驱动。

下一阶段必须处理 LOS 通用驱动到 6.18 的迁移和这些平板接口，再完成有效模块
闭合、合并 DTB/DTBO 绑定、启动包及 AVB 检查，最后在授权后做实机启动和硬件验证。

C 盘本次检查约剩 10.7 GiB；WSL 的 512 GiB 空闲是虚拟磁盘内部数值，不能当作
C 盘还能写入那么多。源码准备工具同时检查宿主空间；目录索引允许在 2 GiB
预算下准备，完整检出/移植构建采用保守的 40 GiB 前置预算。这个预算是本项目
的空间预留，不是参考仓库规定的硬性需求。没有清理其他任务的构建产物或缓存。

## 重跑

```bash
# 获取/复用固定的 LOS Git 目录索引，无完整检出、无编译、无刷机。
python3 scripts/prepare_kernel618_sources.py --catalog-only
python3 scripts/audit_kernel618_sources.py --output reports/kernel618-source-audit.json

# 检查完整构建的预留空间；空间不足返回 2。
python3 scripts/prepare_kernel618_sources.py --preflight

# 检查原厂 BSP 原始文件哈希和 ELF 信息；成功只是清单核查成功。
python3 scripts/audit_kernel618_modules.py \
  --stock-root /root/sheng-lineage/firmware-dump/hardware/modules \
  --output reports/kernel618-stock-inventory.json
```

候选检查时再提供 `--kernel-out`、两个 `--gki-module`，默认要求 6.18。
现有 5.15/6.12 对照必须明确设置 `--expect-series`，不会冒充 6.18 结果。

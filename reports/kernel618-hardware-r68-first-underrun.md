# r68 首次欠载时间定位（2026-11-10）

r67 在 context-deferred（1.0987 秒）尚无欠载，mappings-before-install
（4.0589 秒）两路均已欠载，用户仍确认白屏。本轮只定位第一次欠载事件，
不调整硬件参数。

只读字段及固定来源见 `kernel618-hardware-r67-early-scan.md`。r68 复用相同
资源边界/电源/时钟检查，增加安静读取路径；在 sheng 的 pinned display
context-deferred 后约每 10 ms 采样 IRQ status，最多 3000 ms，发现首次欠载
或访问结束就停止，模块退出会取消工作。无 MMIO 写入、额外电压/时钟投票、
启动停顿或自动重启。参数默认 0；仅本候选 cmdline 开启
`arm_smmu.sheng_scan_watch_ms=3000`。读取指向 DT 声明的寄存器，不读图像内容。

## 构建

- 344 模块 ABI/依赖通过；仅 arm_smmu.ko、dispcc-kalama.ko 改变，其他二进制保留。
- 内核导出一致性、gzip 解压、空 ramdisk、封包回读、AVB 均通过。
- boot SHA256：`667ff726762fc437c92a928fd3f48fe217230318de0e6f7175e8db46a0d300ab`。
- arm_smmu SHA256：`9cfc57761520e185201e168e7e98ee9d3d7efb848ae412aa19aa1aeeadc173d4`。
- dispcc SHA256：`af138d16d3dd06b8247a84024a71e5addd063c05506b4142760677125ad616e1`。

## 实机结果

2026-11-10T07:21:57.9277392+08:00 刷入并重启。revision=hardware-r68，
watch=3000，三个等待参数均 0，Android boot_completed=1，有线 ADB 正常。

- 1.162101 秒启用观察。
- **2.346183 秒首次欠载**，IRQ=`3c000300`；2.349287 秒两路欠载 mask=`14000000`。
- 电源=`f822f800`，AHB/core gate=1，两个图像地址仍为 `b8000000`。
- 两路 intf frame=580、status=`e00`。观察随后停止，未触发期限分支。
- 2.328511 秒相机 SMMU secure component 绑定完成；2.358067 秒 CPAS 绑定完成。
  首次欠载位于 CPAS probe 区间，并早于显示模块接管。相关性不等于已证明根因。

MiCode camera 固定 `ad342a26a37e9fabc2f626a6622b788bf9aa546b`，nuwa
LOS 模块固定 `92a9fde479d3262da080cfd28bab0775b0da500a`。CPAS probe 在读取
版本/初始化时申请并撤销默认 AHB/AXI 投票和资源；MiCode 使用 CAM_SVS_VOTE，
当前集成调用 lowest_clk_level。当前构建实际使用 cam_soc_icc，而非旧 msm_bus。
5.15 与 6.18 的 interconnect 初始投票策略也有差异，尚未隔离是哪一次操作影响显示。

原厂 vendor_dlkm/modules.load 中 camera 在 msm_drm 之前，因此不能声称
“相机提前加载”是本移植独有差异。r69 将用相同驱动二进制，让显示及其
必要依赖先建立 Linux 资源投票，再加载相机，测试能否保护固件画面的接管。
没有删除或跳过相机功能。原始日志：`reports/device/kernel618-hardware-r68/kernel.txt`。

本轮只读诊断未宣称修复白屏，最后视觉验收仍为 r67 白屏。

原厂模板只读，仅刷 boot_a，四项 Fastboot 身份检查通过；不擦分区、不备份
当前 boot、不内置 root、不启用定时重启或循环刷写。交付 r64–r68 共五版。

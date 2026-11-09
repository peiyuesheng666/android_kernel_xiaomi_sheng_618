# r60 显示时钟接管对照（2026-11-10）

用户最新验收明确手写笔及其他功能均已修好；当前持续目标只剩开机白闪和
重启后首次解锁前没有充电提示音。停止改动已验收的笔、键盘、USB 等路径。

## 来源和候选

- piano 设备参考固定 `82adb0a5e072aeb90292ad4adff1d92a21580f12`，BoardConfig 使用独立 piano-kernel 预编译/头文件，不能直接导入其平板显示硬件参数。
- nuwa 共用 LOS SM8550 内核固定 `f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d`，`clk_lucid_evo_pll_configure` 在写寄存器之前检查运行状态；OLED 手机不提供 sheng N81A 复位/时序依据。
- MiCode sheng 内核固定 `29db5d592c5b577aa9d9611da988a5e071d100dd`，同样先检查运行状态；当前集成 ACK helper 会先改 PLL 输出掩码再判断已启用。
- r59 日志：PLL0 USER_CTL 由 1 改为 7，MDP CFG 由 `0x105` 改为 `0x100105`，MISC_CMD 由 0 改为 `0x10`。

候选仅在精确 DT model `Qualcomm Technologies, Inc. 8550 sheng` 且 MDP
已运行时保留 PLL 的已有输出/分频配置，将 MDP 硬件门控切换推迟到
sync_state；其他机型沿用原配置路径。板级 DT compatible 是通用 kalama-mtp，
不能据此识别 sheng。未运行的 PLL 仍用原 helper 初始化，读失败返回错误。

## 验证与实机结论

- 344 个模块 ABI/依赖通过；相对 r56 仅 `dispcc-kalama.ko` 字节变化，其余模块保留。
- 生产 PLL helper 的运行状态、停用状态、两处读失败、普通机型路径，通过 ASan/UBSan 检查。
- 内核导出保持原构建清单；gzip、空 ramdisk、封包回读和 AVB 验证通过。
- boot SHA256：`32f6cf63c4867eebca8c9606de38564ba122417fa86eb129739f3e2545ef338c`。
- dispcc 模块 SHA256：`afd9329ea8aa311dd810e8ad7d710e0282576bfa547529ace66e6b5f187d5ce9`。
- 06:23:39 +08 刷 boot_a 并重启；核对 sheng、a 槽、解锁、非 fastbootd。保留 r56–r60 五版。
- 实机 revision=hardware-r60，boot_completed=1，USB CONFIGURED、online=1。
- 0.411132–8.419014 秒执行等待；8.974969 秒明确记录 retain live PLL0，12.112495 秒记录 consumers-bound。
- **用户确认白闪仍出现；此候选未修复白闪。** 准备将唯一 8 秒等待移到 DISP CC 注册之后，继续缩小故障阶段。

本地原始日志：`reports/device/kernel618-hardware-r60/kernel.txt`。
原厂包只读，仅刷 boot_a、不擦分区、不备份当前 boot、不启用定时重启。

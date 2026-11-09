# release-r70 实机交付（2026-11-10）

用户确认 r69 白屏消失后，要求关闭测试日志、等待和键盘诊断输出，构建
release、实际测试开机并交付。随后要求先交付内核，源码包晚点整理。

release-r70 保留 r69 的完整 344 模块集合与加载顺序；显示及其依赖先于
camera 加载。只重编 arm_smmu、dispcc-kalama、qti_battery_charger、
nanosic_driver、msm_drm 和 k618_load，关闭相关调查输出。

- CONFIG_SHENG_BOOTLOG=n；vmlinux 符号检查确认 rawdump 日志和测试重启
  实现没有编入。恢复基线 LOG_BUF_SHIFT=17。
- 移除显示入口、显示时钟等待参数，探针等待、SMMU 扫描工作队列和只读
  寄存器扫描；模块字节检查确认相关日志和 TEST_ONLY 标记不存在。
- 关闭键盘信息日志，保留认证传输、固件加载、连接和实际断开处理及错误报告。
- 保留 GKI ABI 所需的原有配置与 DWARF/BTF；未把 upstream 的 ABI 相关
  调试设施全部删除。原厂启动参数仍包含 kasan=off 和原厂日志设置。
- kernel 与基线的 18008 个导出及 CRC 完全一致；344 模块 ABI、depmod、
  封包解包及 AVB 检查通过。没有内置 KernelSU/SUSFS。

2026-11-10 07:38:46（UTC+8）在核实 sheng、slot a、unlocked yes 和
is-userspace no 后仅刷 boot_a；24.67 秒 USB ADB 返回，25.19 秒 Android
启动完成。90 秒观察截止仍可执行 ADB。用户确认「白屏消失，键盘和触控板正常」。
此验收不等同于重新验收所有硬件。前后相机 NDK 帧探针均能打开并建立会话，
但取得 0 帧，不能计为相机帧验收通过；执行时设备 keyguard showing=true。
历史 r29 同类探针也记录过 0 帧，未据此宣称新的相机根因。

## 交付

- boot.img SHA256：777c2e37a3ece8e685845a7ae13dc9c3c0b6f8189f2fd6e038fa7d8faf13d144
- Image SHA256：6959f15542487c389c108d0504646d2317e33bdadb26a57cfc4a60ef1cb8cda5
- 目录：artifacts/sheng-6.18-release-r70（映射到 E 盘 artifacts）。
- 证据：reports/kernel618-release-r70-hardware.json、
  reports/device/kernel618-release-r70/runtime-kernel.txt。

源码 tar.gz 尚未交付：精简导出已开始，但检查发现 ACK 源码中残留未启用的
KernelSU 绝对符号链接，打包程序正确拒绝导出。需要排除该未启用链接及
核对完整构建输入后继续。尚未删除工作树 out 或其他编译目录，避免在用户
要求先交付内核时破坏后续整理所需的输入。

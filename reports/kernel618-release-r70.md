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

## 精简源码交付

用户要求继续整理后，完成 `sheng-6.18.32-release-r70-source.tar.gz`，
317926350 字节（约 303.2 MiB），含 103647 个普通源码及配置文件。
源码包保留 ACK、SoC、techpack、平板适配源码、344 模块构建路径和 r69
显示优先加载清单、实际 release 配置、打包工具与独立 Linux/WSL 构建入口。

排除 out、对象和模块二进制、编译缓存、Git 历史、工具链、ROM 镜像、测试
抓取及 rawdump 日志。排除未启用的 KernelSU 绝对链接及 SUSFS 实现，并
从导出副本移除对应 Kconfig/Makefile 引用，避免干净配置读取缺失文件。
原 ACK 条件集成守卫仍保留，release 配置不启用它们。

精简源码的独立 `olddefconfig` 检查通过，测试日志及内置 root 配置保持关闭；
清理涉及的硬件源码与 r70 已记录的哈希逐一匹配。tar.gz 全部普通文件的
SHA256 回读匹配，路径及符号链接检查通过。未另行完成干净源码的全量重编；
已实机验收的是先前对应工作树构建的 boot.img。工具链需按包内说明另行准备。
源工作树编译目录保留，交付源码副本不含这些目录。

- tar.gz SHA256：7c054599ce763bbbd75f21dccfc77102b2fb55f3dacb3f25c2d4d4ed03cef437
- 证据：reports/kernel618-release-r70-source-package.json；源码包内 SOURCE-SHA256.json。

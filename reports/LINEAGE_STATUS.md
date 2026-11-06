# 当前 LineageOS 工作约定

- 产品：Xiaomi Pad 6S Pro 12.4，代号 sheng，SM8550/Kalama。
- 首轮：LineageOS 23.2 / Android 16，官方 LineageOS SM8550 5.15 内核。
- 6.12 在类原生系统完成之后进行；已编译的 ACK 基线不代表设备适配完成。
- piano 只作参考，不使用其整棵设备树或预编译内核。
- 原厂 OS3.0.303.0.WNXCNXM 线刷包目录只读。提取结果、脚本及修改均在该目录之外。
- 所有构建写入 C 盘 WSL ext4：`/root/sheng-lineage`。
- 用户最新设置：全线程24路；swap总量80 GiB（默认12 + 原48 + 新20）；
  压缩ccache限制10 GiB。脚本 `rom_build_settings.sh`，严禁续作时误改回2线程/60GiB。
- 先前准备的 E 盘 ext4 空白容器不再使用，尚无 Android 源码写入其中。
- 当前阶段：平台源码同步中，自行编写的设备配置初稿已放入 `device/xiaomi/sheng`，
  该初稿存在明确待完成项（见其 `docs/BRINGUP.md`），未生成 LineageOS 刷机产物。
- 尚未进行刷机或实机开机验证。

## 2026-11-04 22:37 续作检查点（北京时间）

- 自动化 ID `sheng-lineageos` 已纠正：2026-11-05 02:54 开始，每小时续作。
  成功交付后结束自动化。遇限额查询真实重置时间调整下次续作。
- `repo sync` 已在 C 盘工作目录启动，日志 `/root/sheng-lineage/logs/repo-sync.log`。
  检查进程后再操作，避免同时启动第二个全量同步。最近 `.repo` 约 3.7 GiB。
- 官方依赖清单 `manifests/sheng.xml` 已安装到 `.repo/local_manifests/sheng.xml`。
  此安装发生在第一轮同步启动后，第一轮结束后必须再次同步以获取这些依赖。
- `scripts/setup_rom_workspace.sh` 已改为 C 盘原生 WSL ext4，不再创建或挂载 E 盘容器。
- `scripts/unpack_stock_super.py` 已校验 sparse/liblp 元数据并提取 8 个非空分区到
  `/root/sheng-lineage/firmware-dump/images`，每个镜像有 SHA256。
- `scripts/extract_stock_files.sh` 已从 C 盘镜像只读挂载并复制全部文件到
  `/root/sheng-lineage/firmware-dump/partitions/{vendor,odm,product,system,system_ext,vendor_dlkm,system_dlkm,mi_ext}`。
  8 个分区均有 `.分区.complete` 标记。输入线刷包未修改。
- 已验证 super = 11811160064、boot = 100663296、dtbo = 16777216 字节。
  设备配置覆盖了手机 common 的不同分区尺寸。动态组容量需继续核对 liblp group 字段。
- 原厂 vendor build.prop 报 Android13/SDK33、ODM first API34、24018RPACC。
- 原厂 vendor_dlkm 有 304 个 ko，modules.load 包含 nt36532_touch、fpc1552、
  nanosic_driver/platform 和 cs35l43_dlkm，不能照搬参考项目不同版本模块名。
- 官方 LOS kernel23.2 是5.15.211，缺 sheng_GKI.config，官方 DT/模块对 sheng 的
  板级支持尚未完成。必须处理此项，不能用通用内核冒充完成适配。
- 初稿 `AndroidProducts.mk` 暂列 `bp2a`，需用实际23.2平台 release config 核实。
- 已获取的参考树在 `/root/sheng-612/reference`，piano、社区 sheng 只读参考；
  官方 common 的共享实现允许使用。没有复制其整棵设备树。
- 下一步：完成官方平台及设备依赖同步；核对 lunch release；由本地原厂提取物生成
  vendor 清单和 makefiles；完成 sheng 板级内核/模块/DT 配套、HAL/overlay/init/policy；
  实际完整 `m bacon` 并修复失败。暂不构建 PixelOS/Evolution X，不迁移6.12。

## 2026-11-04 23:10 最新检查点（优先于上文历史记录）

- 用户要求先完成编译前准备再等待同步，当前独立于平台源码的准备已完成并通过检查。
- Host依赖安装完毕：日志 `/root/sheng-lineage/logs/dependencies.log`，包版本清单
  `/root/sheng-lineage/logs/installed-packages.tsv`。使用平台manifest固定的JDK/Clang实际构建。
- 已确认官方23.2的aosp_current指向bp4a，lunch入口改为 `lineage_sheng-bp4a-userdebug`。
- 设备树有真实分区覆盖、kernel fragment、DTB/DTBO输入、音频/ACDB、FPC侧边指纹
  属性和init/SELinux、Wi-Fi平板overlay、专有文件清单、extract/setup脚本。
- 手机公共产品配置经明确的章节转换生成 `platform/common-tablet.mk`，保留Lineage版权。
  没有修改参考common源码；不引用piano的文件或预编译内核。
- sheng专有文件清单1254项，含根据实际ELF NEEDED递归补齐的153项依赖。
  清单和生成器在工作区；公共vendor清单仅取该平板固件实际存在的项目，移除外部固件hash。
  vendor提取与生成成功，无提取错误：`/root/sheng-lineage/logs/vendor-extraction.log`。
  已安装到ROM的 `vendor/xiaomi/{sheng,sm8550-common}`，文件均来自本地原厂提取物。
- 修复原厂三份motiontuning XML的错误声明，仅改提取副本；修复一个库的Soong模块重名。
- 官方kernel仍源码编译；首次同LTS移植先用原厂sheng DTB/DTBO。
  原厂板级模块15个在 `device/xiaomi/sheng-kernel/stock-modules`（仅C盘WSL中有二进制）。
  自主编写的external module installer接入官方构建，在编译后检查所有导入符号和CRC，
  不兼容则明确失败，不改vermagic、不关闭MODVERSIONS、不静默忽略错误。
- ELF CRC解析已与kmod核对15个真实模块。额外用合成symvers验证安装器：正确CRC接受、
  错误module_layout CRC拒绝且不安装。测试见 `reports/module-guard-tests.json`。
  这不是与新kernel真实ABI匹配的结论，真实匹配要等kernel编出之后。
- `reports/lineage-preflight.json`：preparation_checks_passed=true，5个官方源码依赖等待同步。
  检查包括shell/python/XML、vendor模块重名、15个board ko、swap和host依赖。
- 首轮全平台同步仍PID101，日志repo-sync.log（网络阶段输出较少，检查git子进程进度）。
  第二轮需要设备依赖，已经启动 `continue_after_sync.sh 101`，最近PID43590，
  unified exec session61252。它等待初始进程退出后做最多3轮repo sync -j6，
  成功后写synced并执行build_lineage.sh，按24线程编译；不要重复启动。
- 构建日志build-lineage.log，构建状态build-status.txt，续同步日志repo-sync-final-N.log。
  build_lineage先验证完整同步，再lunch和m bacon。失败后需读日志实际修复再续。
- export_lineage.py仅成功后导出ROM zip+7个镜像及SHA256、源manifest、ABI报告到
  Windows本项目artifacts目录；不自动刷机。当前仍未编译出Lineage ROM。
- 最后C盘实际约329 GiB可用。WSL显示的733 GiB是虚拟ext4上限，不能当成物理可用。
  swap的未写extent可随实际换页增长VHDX，后续必须继续看C盘真实剩余空间。
- 自动化sheng-lineageos已同步24线程/80GiB swap/10GiB ccache最新偏好。

## 2026-11-04 设备复查与完整提取后的最新约定

- 用户质疑型号/完整度后进行了实质复查，见 `reports/SHENG_DEVICE_AUDIT.md`，优先于旧检查点。
- 型号24018RPACC、代号sheng、商品名PRODUCT_MARKETNAME分开；原厂ODM为身份依据。
- 修复eUICC小写标题漏删及GNSS/IR/手机overlay/IMS属性残留，增加独立fstab及触摸早期固件、
  pen idc/kcm、原厂声卡/麦克风配置、原厂亮度与10000mAh功耗模型。
- 原厂专用模块现在17个，不是旧记录15个；新增xiaomifp和xiaomi_wifi_gpio。
  export/preflight使用sheng-stock-preparation.json动态核对列表，不把数字写死。
- hardware目录全量缓存27个启动/固件镜像，640个ko文件条目、5241项文件清单及SHA256；
  DSP/modem/蓝牙已解包。原厂E盘目录没有写操作，后续设备准备读取C盘缓存。
- `derive_stock_overlay.py`用Google Maven官方aapt2 8.7.3-12006047解出硬件资源；
  overlay已通过aapt2 compile。此结果不是完整平台RRO链接或实机验证。
- 自动化ID仍sheng-lineageos，最新名称“源码同步完成后继续 sheng 编译”：
  北京时间11月5日02:54起每10分钟只读检查。源码未齐且同步健康就安静等待，
  不重复拉取、不提前编译、不开展设备修改。若同步失败，只修复同步后继续等待。
- 全部平台+官方设备依赖同步成功后，现有continue_after_sync.sh会接续构建；
  检查其进程/日志再操作，禁止重复启动。开始编译/需要处理失败/产物完成时通知用户。
- 复查期间设置的logs/device-audit.pending仅用于阻止旧配置自动开编；
  本次已知配置问题通过增强前置检查后可解除，不能因为检查放行而声称设备已开机。

## 2026-11-05 独立配置（最新架构，覆盖此前继承方案）

- 用户明确要求像piano那样独立配置。已从运行/构建/提取中去掉sm8550-common。
- `device/xiaomi/sheng`现在直接维护BoardConfig、约400行device.mk、rootdir、configs、
  module lists、properties、overlays、VINTF、SELinux、fixups。参见本树README。
- 私有文件统一2027项，extract-files.py仅创建sheng模块，不动态导入其他设备；
  新sandbox为 `/root/sheng-lineage/extraction-standalone`，成功生成单一vendor/xiaomi/sheng。
- 新prepare_sheng_stock.py仅检查/刷新本树已审批清单和C盘原厂缓存，不再生成公共产品配置，
  不再读取参考common树。请勿恢复已归档的platform/common-tablet.mk方案。
- 必要通用高通脚本/策略来源保留原许可证。`reports/standalone-migration.json`记录
  75项来源/哈希与固定提交；materialize_standalone.py仅是一次性历史迁移工具，不是构建步骤。
- 原WSL设备树和两个vendor目录已移到 `/root/sheng-lineage/archive/pre-standalone`；
  ROM运行目录无device/xiaomi/sm8550-common及vendor/xiaomi/sm8550-common。
- 清理无对应服务的NFC/MLIPAY/IR策略引用及IR模块load，补充源码wl2866d/wl2868c/xiaomi_touch加载。
- manifest和lineage.dependencies只要求4个官方源码repo：hardware/xiaomi及SM8550 kernel/modules/DT。
  首次同步仍在运行；后续sync会使用已更新的4仓库清单。
- verify_standalone.py已核对没有旧设备路径、所有本地src输入、全部XML/脚本，以及无公共树时的
  GNU make板级值（分区/属性/模块/目标平台）。这不是完整Android Soong/Kati构建。
- preflight已接入独立检查，下一轮构建仍需通过--require-synced和实际模块CRC检查。
- 24线程/80GiB swap/10GiB压缩ccache、原包只读、源码未齐就等待等用户约束不变。

## 2026-11-05 切换24.0及新增Dolby目标（最新）

- 用户明确选择LineageOS24.0，并撤回删除23.2的指令，最终同意复用已有Git数据。
- 已停止原23.2同步和旧等待进程，将原源码目录直接重命名为
  `/root/sheng-lineage/lineage-24.0`，未删Git对象、设备树或stock缓存，也未复制第二套完整源码。
- repo init已切到lineage-24.0；官方manifest是android-17.0.0_r1。
  AOSP17 release_config_map中aosp_current=cp2a，入口已改为lineage_sheng-cp2a-userdebug。
- 官方hardware/xiaomi及SM8550 kernel/modules/DT的24.0分支均用git ls-remote核实存在。
  web页面有404缓存，不能据此断言分支不存在。官方kernel24 Makefile为5.15.220。
- 实际运行脚本路径均已更新24.0，旧审计工具/一次性迁移的23.2文字是历史来源，不应重跑。
- 新continue_after_sync.sh无旧PID等待逻辑，持有continuation.lock，setup80GiBswap后同步24.0，
  最多3次重试、日志repo-sync-24-N.log，成功后生成source-manifest并启动build_lineage。
- 迁移过程中build/release、external/aac等项目来源改变导致hooks不同，已对任务自有平台repo
  使用 --force-sync 重建Git元数据连接，保留源码对象，未触碰独立设备/vendor数据。
  当前unified exec session1033正在运行新版同步/构建管线。
- 旧23.2进度为完整清单1168/已获取989/待179（7只是已启动未结束的下载，不能报仅剩7）。
  24.0必须按目标revision重新统计；measure_sync_progress.py有30秒接收速率与目标版本可用数。
- 用户新增Dolby Atmos要求，尚未完成！当前原厂已缓存完整Dolby DMS HIDL2.0服务、库与配置。
  vendor/etc/audio/sku_kalama/audio_effects.xml实有dap/libhwdap.so，UUID
  9d4921da-8225-4f29-aefa-39537a04bcaa，以及dvl/spatializer/gamedap/vqe。
  vendor/etc/init/vendor.dolby.hardware.dms@2.0-service.rc与对应VINTF均在本地stock中。
  必须补提取清单、依赖、音效XML、DMS策略/兼容矩阵、控制入口并验证，不得只加APK声称生效。
- 注意libdolbyproxyandroid.so和libdolbyeffect.so是Dolby Vision组件（已查字符串/依赖），
  不要因名字把它们当作Atmos客户端。Atmos的可控效果是vendor libhwdap的AudioEffect接口。
- 旧extract-files.py仍有删除Dolby codec2声明/媒体codec的fixup，应审视恢复配套；
  用户要求Atmos不等于要求盲目加入所有Dolby Vision组件。保留真实原厂授权/资源，不伪造能力。
- 用户问piano AIDL目录：实际本地实现lights、sensors、LiveDisplay；interfaces/hypsys另有小米扩展。
  sheng已有官方hardware/xiaomi AIDL指纹/传感器调用。是否另写本地实现取决于实际接口，不能复制SM8750实现。
- 当前logs/device-audit.pending仍存在，表示Dolby/新增接口适配待完成，挡住自动开编。
  完成集成与检查后可自行解除，不需用户再次授权。不要留下标记却声称能自动编译。
- 定时已更新IDsheng-lineageos，名字“额度重置后继续 sheng LineageOS 24”，ACTIVE。
  实际短周期额度已用79%，重置北京时间11月5日02:52:47；02:54起每10分钟检查。
  源码未齐就安静等待，齐后按最新24.0+独立配置+Dolby目标继续，直到成功交付。

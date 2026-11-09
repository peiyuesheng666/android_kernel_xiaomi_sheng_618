# 6.18 sheng 外围实机修复

## 2026-11-09 r37 USB / 相机候选与 5555 模块实机

r36 后续实际回读确认 hardware-r36，root / su 可用、Android 启动完成。
USB 在启动经过 2458668 ms（约 41 分钟）才连接，与用户“约四十分钟”反馈
一致；不是五分钟观察未见就停止。dmesg 单调时间不含休眠，不能用 978 秒
替代 Android 的开机经过时间。连接恢复后 USB 为 CONFIGURED/UFP/device/sink。
已保存故障 bugreport、完整 root 内核及 logcat 日志。

相机日志在 IFE_FD (0x3004) 输出捕获到 SMMU 越界：614400 字节 NV12 映射
末端 0xffee96000 被访问；852×480 的 Y/UV 行跨度均为 852，UV 偏移409088。
新通用驱动把 IO stride 实际上取整为 864，UV 最后一行写到616436，超出
分配。固定 LOS/MiCode sheng 5.15 均写原始 stride。r37 仅在 VFE780 且无
明确 WM stride 覆盖时恢复原始 IO stride；其他型号和覆盖值保持原逻辑。
编译实际生产选择语句的旧/新缓冲边界对照通过，旧 camera ELF 被拒绝。
此结果尚不等于预览、反复录像或上下移动绿屏已修复。

USB 候选保留原 PHY XO_PAD 参考时钟投票，只在精确 sheng 型号和 GCC 主
pipe mux 上使用该 mux 真正的 bi_tcxo 父时钟休眠，避免已确认的选父失败。
SoC/camera 重编、344 模块的20984项导入CRC、18008内核导出、归档权限、
来源哈希、AVB 和 boot 解包回读通过。r37于18:09:30仅刷boot_a，用户确认
进入桌面；交付保留 r33–r37 五版。
不内置 GKI KSU/SUSFS，不带定时重启，仍只刷 boot_a。

已通过现有 /data/adb/ksud 安装用户授权的 5555 模块 v2（1.1），当前启动
手动运行后 192.168.1.153:5555 已实际连接并执行 root 命令；ro.adb.secure=1，
SELinux Enforcing。v2 移除无效的 settings Binder 操作，运行日志无相关失败。
不写持久 ADB 属性，保留认证；r37重启后18:10:17模块自动执行，约77秒
实际连接5555并读取root命令，开机自启已验证。
详见 kernel618-camera-io-stride-source.json、kernel618-ssphy-pipe-xo-source.json、
sheng-adb-5555-module-v2.json 和 r36 followup。炸音、白闪/速度及长期传感器
休眠恢复仍继续处理。

r37用户随后确认反复录制、向上移动、退出重开均正常，未再出现底部绿色或
卡死，记录为本次相机验收通过；实机三个VFE780核心均启用原始IO stride，
后续日志未见原IFE_FD SMMU越界，仍有sync对象告警，不虚报所有模式长期稳定。
USB选父告警已消失，但301.35秒观察依旧无有线ADB；用户重插后仍不识别
且不充电，故USB未修复。早期及重插后的UCSI固件GET_CONNECTOR_STATUS
均返回未连接，USB ONLINE=0、VBUS约0.43V、CC orientation=0；控制器UDC
存在且配置了ADB，问题已定位到连接检测/充电与Type-C链路，继续调查。
固件原始UCSI与DWC3 IPC日志已保存；详见kernel618-hardware-r37-followup.json。

## 2026-11-09 r36 候选与 root 范围

按用户最新指令去掉内置 GKI root；核心与最终内嵌 Image 都没有启用的
KSU/SUSFS 配置或相应定义符号，已用旧 r35 的真实已启用配置验证拒绝。
管理器版本继续暂缓；用户随后明确授权制作开机无线 ADB 5555 模块。
安装包已构建，主机语法、归档权限和启用/权限失败/早启动/停止恢复流程检查
通过；最初 192.168.1.153:36911 连接超时，后续 v2 安装和当前启动验证见上。
模块保留 ADB 身份认证，不写 persist.adb.* 或修改 SELinux 模式。

收尾已有 EVA 配置调查：选定上游 k618_rpc515.sh 明确为 EVA 传入
CONFIG_MSM_ADSPRPC=1，通用重编路径此前遗漏，fastrpc.h 因而内联为返回零
的占位函数。恢复该定义后，msm-eva.ko 实际导入三个 FastRPC 驱动接口，
重编、清单、封包三级检查通过；旧 r35 EVA 被拒绝。
344 模块、20975 项版本化导入、18008 项内核导出一致性、归档权限、
来源哈希、AVB 和官方 boot 模板解包回读通过。交付仅保留 r32–r36 五版。
17:12:48 仅刷 boot_a，300.36 秒有线 ADB 未出现，不带定时重启。
用户起初确认录像可录制，但向上抬时相机预览与保存的视频底部均有绿色，
随后报告相机再次卡死甚至绿屏，录像仍未修复。关闭防抖对照没有得到有效
结果；目前不能确认绿色来自防抖、时间戳、缓存或同步错误，须抓当次故障日志。
后续已回读实际 r36 身份并抓取故障日志；USB、炸音、白闪及启动速度仍未验收。
完整证据见 kernel618-root-removal-r36.json、kernel618-eva-fastrpc-config-r36.json
及 kernel618-hardware-r36-{layer,boot,hardware,followup}.json。

## 2026-11-09 r35 实机与持续修复约定

16:41:54 校验 product=sheng、a 槽、unlocked=yes、is-userspace=no 后，
仅刷已验证 r35 的 boot_a 并正常启动，不带定时重启。300.4 秒观察未收到
有线 ADB；用户确认已进入桌面，提供新无线端口 192.168.1.153:41129。
实际 banner 为 16:36:36 构建的 r35，bugreport 内核命令行含 hardware-r35。
Android boot_completed=1，SELinux 保持原厂 Enforcing。

两次 sensorservice 采样均有 54 项，包含加速度计、陀螺仪与设备方向；后次
加速度事件更新至 516 秒，陀螺仪也有真实样本。当前 bugreport 内核段原来的
fastrpc_session_alloc failed 完全消失。已证明传感器数据通路恢复，不能用
这段观察代替长期休眠/唤醒和自动旋转稳定性验收。
USB 仍为 DISCONNECTED、none/no-power/no-data，电池未充电，SS PHY 的
pipe_clk set_parent disable 告警仍在，不能视为 USB 已修复。
扬声器炸音、视频录制、白闪和启动慢继续处理。模块差异审计另发现 r33
以后 EVA 缺少三个 FastRPC 导入，正在修正相关配置，尚不宣称录像恢复。

用户要求设定持续目标并一直修复；本轮不因五分钟无有线 ADB 停止。
test_sheng618_normal_boot.py 保留旧停止条件作为显式选项，默认记录结果后
继续排查。误解用户“无人值守”而创建的 heartbeat sheng-6-18 已删除。
当前持续目标仍 active。最新 root 指令为下一版去掉内置 GKI root，不处理
管理器版本，也不创建模块；只有用户明确说可以做模块后，才制作开机开启
无线调试端口 5555 的模块。当前 shell 没有 su，不假定已获 root。
完整哈希与范围限制见 kernel618-hardware-r35-followup.json。

## 2026-11-09 下午 r35 FastRPC 厂商配置回归修复

用户重新要求继续修复，并补充 USB 开机后不可用、过几十分钟自行恢复，方向
传感器间歇失效，充电提示音等扬声器输出偶发炸音，拍照可用而录像失败。
16:23–16:25 有线 ca10ede3 实际响应，运行 r34、boot_completed=1、SELinux
Enforcing；USB 为 CONFIGURED、UFP/device/sink，电池报告充电中。
当前 sensorservice 只有 Dynamic Sensor Manager，没有加速度计或陀螺仪。
该恢复发生在旧 r34 上，不能视为本轮修复的效果，USB 延迟根因仍未确认。

本次只读 bugreport 的内核段有 2489 条 fastrpc_session_alloc failed/ret -87
记录；adsprpcd 和 sscrpcd 的监听线程反复得到 ENOSR 并重新初始化。
对照固定上游 c3956156ce7c4193c451dfda531fad72d35bfebb 的 k618_rpc515.sh、
LOS nuwa f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d 的 mem-buf.h，发现本项目
rebuild_sheng618_modules.py 的 native-adsprpc-515 与 rpc-before-eva 两处漏带
tp-autoconf.h。实际 r34 ELF 缺少 mem_buf_dma_buf_exclusive_owner、
qcom_register_ssr_notifier、msm_minidump_add_region、qcom_elf_dump 四个导入。
早期 tablet-r20 同名模块保留全部四项，区别不是单纯日志告警。

选定 SoC 的 mem-buf.h 在 CONFIG_QCOM_MEM_BUF_DEV 未启用时将所有权 API
替换为 static inline false。fastrpc_mmap_create 因而将普通缓冲误判为安全缓冲，
请求 secure=1；sheng 原厂 ADSP context banks 都是非安全，故返回 EUSERS。
调用方转为 ENOSR，即当前监听线程的 Out of streams resources。这里的
“max concurrent sessions”告警不足以证明真正泄漏或耗尽 12 个普通会话。

两处重编恢复上游同样的 SoC 头文件优先级和强制厂商配置，保留原厂安全归属
API，不改其返回值或安全会话数量。新增真实 ELF 导入门槛，在两处 FastRPC
重编后、完整模块清单和最终封包时检查；旧 r34 被拒绝，早期模块和重编模块
被接受。FastRPC、EVA 以及板级模块重编通过，其余模块沿用 r33/r34 同一
release 的真实重编输出；344 项清单来源哈希已核对，未二进制改 CRC/vermagic。
r35 候选已构建，344 模块 ABI、18008 项内核导出、归档权限及官方 boot
封包回读检查通过。尚未刷入，无自动重启。恢复传感器、扬声器及录像均待实机
验证，不能从编译成功推定三项问题已经解决。

原始日志保持在忽略目录，整理报告为 kernel618-fastrpc-config-source.json，
包含 bugreport、前后 ELF 与固定参考文件哈希以及已知坏模块拒绝结果。
交付目录按既有约定保留 r31–r35 五版，移除 r30 交付副本；原始线刷包只读。

## 2026-11-09 无线调试恢复助手与三分钟停止条件

用户先撤销了 r34 的“仅有线 ADB”继续条件，要求无线 ADB 可用也继续修复，
并要求无 root 的无线调试开机恢复。已构建并通过原有无线配对安装
org.peiyuesheng.sheng.adbboot，一次性授予 WRITE_SECURE_SETTINGS、后台运行
及电池白名单，07:49–07:50 重启前日志确认 adb_wifi_enabled 写入并保持为 1。
使用公开 SDK 36、开机广播和有网络条件的持久任务；保留框架的可信 Wi-Fi
与配对检查。澎湃 AUTO_START appop 不识别，未据此宣称已获得厂商自启动许可。

用户手动重启后最后要求“等三分钟，不行停止”。观察窗口为 07:52:17 至
07:55:17 +08；07:56:11 主机检查仅有离线 TCP 连接，无有线设备，mDNS 服务
列表为空。因此停止设备调试和刷机，不再抓日志、重启或刷下一版。
主机发现脚本此前在已知无线连接可用时也未发现服务，因此未连接不能单独
证明助手未启动；这次重启自启动结论为未验证。端口探测受主机代理假阳性
干扰，已中止，32768/32769 不作为设备有效端口或内核故障证据。

APK 签名与源码哈希已核验；不改 root、配对验证或充电参数。未新增内核版本，
仍保留 r30–r34 五版。USB/充电、启动白闪、间歇键盘/触控板、相机录像卡死、
插电音效卡顿及流畅度均未宣称解决。构建记录见 sheng-wireless-adb-boot-build.json，
本次结果见 sheng-wireless-adb-boot-test.json，使用限制见助手目录 README.md。

## 2026-11-09 r34 开机背光及澎湃 USB 接口候选

本轮按用户新约定：只刷 boot_a，正常构建无自动重启；重启后完整观察
300 秒，只以有线 ca10ede3 的 ADB 及实际 shell 响应作为继续条件。
无线 ADB 不替代 USB 验收。五分钟末有线 ADB 仍不可用就停止后续修复，
只整理本轮记录；不自动切 Recovery 或再刷下一版。

开机显示对照固定 MiCode 显示 6461221b68908b990e1fa2b60feaa812cb944ef5、
LOS nuwa 显示 92a9fde479d3262da080cfd28bab0775b0da500a，恢复已有原厂 DT
初始亮度 307，限于 N81A 外置背光面板；此前通用路径设为最大值 4095。
去掉本项目 r31 加入的 KTZ probe 关背光，保留实际 panel reset 前的关灯。
r33 此处两盏背光在 13.32 秒熄灭，直到 40.94 秒才重新非零，存在约 27 秒
黑屏空档。脚本、补丁、不可变源副本及哈希见 kernel618-boot-handoff-source.json。
用户对 r34 的实测仍为“白一下屏然后进入小米 Logo”，因此白闪未修复，
黑屏间隔和完整开机时间尚未量化，不能声称显示问题全部解决。

USB 对照固定 LOS f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d 与 MiCode
29db5d592c5b577aa9d9611da988a5e071d100dd。LOS 没有 enable_msflag 私有 ABI；
MiCode 只对 M2/M3/N11 特定地区开启该方案，sheng/N81A 返回 0。本轮仅在
已核实的 sheng model 上恢复 /proc/enable_msflag 的只读 0，随驱动注销清理。
原厂 USB HAL 高频读取缺失节点并报 ENOENT，已保留原始日志；不能将该缺口
等同于枚举失败的根因。中继器解析额外接受原厂 qcom,param-override-seq-host
别名，现有 qcom,host-param-override-seq 优先；不改 device 模式调参。
源核查见 kernel618-usb-hyperos-source.json。UCSI sync_control 回读接口与
6.18 core 合同匹配，此处未改。SS PHY 父时钟警告仍未解决。

本轮重编 SoC 模块和 display，使用 r33 同一身份真实重编的其他模块，
未修改二进制 CRC/vermagic。344 模块、20964 项导入 CRC、18008 项内核导出、
归档权限、来源哈希链、官方 boot 模板解包回读检查通过。固定版本及用户/主机
保持 6.18.32-peiyuesheng-sheng-kernel、peiyuesheng@MiFans。
07:37:08+0800 已仅刷 boot_a，07:42:09 完成 300.81 秒有线检测，全程未见
ca10ede3 的 ADB，stop_required=true。按用户规则停止后续修复和刷机，未切
Recovery、未构建或刷入 r35。正常系统启动与 USB 枚举分开记录。
无自动重启，官方包只读，交付目录保留 r30–r34 五版。
Image SHA256=e80d81154e91e7bad2f1c3061fcd06402b1c155976c54d016fcc686ef2033dc3；
boot SHA256=c0743ff5824c4a20158f7bea5f5aa13e7881de5e2e74385b91e1885e3f2237ce。

用户在截止前接通已配对无线 ADB 并明确要求抓 USB/充电日志；已用新端口
192.168.1.153:33289 完成只读采样和 bugreport，未以无线连接替代有线验收。
实机 banner 构建时间为 07:35:59、boot_completed=1。当前 KERNEL LOG 的
13.599703 秒确认初始亮度 307；探测阶段没有原关灯动作，但用户仍观察白闪。
35.501575 秒 UCSI 1.10 已探测，36.642169 秒初始角色 NONE，89.212862 秒
短暂切 HOST，89.727609 秒回 NONE，dumpsys 记录连接持续 515ms。
这段切换未与具体插线动作可靠同步，不能断言错误识别了哪种外设。
采样时 Type-C disconnected/no-power/no-data，电池 USB powered=false、
最大充电电流/电压均为零；用户反馈充电宝显示 4.9V、无瓦数。
该证据表明问题不限于 ADB 服务，但尚不足以确定连接掉线和充电失败根因。
SS PHY 的 pipe_clk set_parent disable 告警仍存在；未修改充电电流或保护设置。
原厂 SELinux 拒绝 shell 直接读 dmesg、部分 sysfs 和 enable_msflag；当前内核段
由 bugreport 正规获得，未降低 enforcement，也未将拒读误报为节点缺失。
原始日志继续忽略，不入 Git；哈希与限制见 kernel618-hardware-r34-followup.json。

键盘/触控板休眠后可靠性、相机录像卡死、插电音效卡顿及流畅度仍未验收；
本轮没有将调频、录像或键盘标为已修复。

## 2026-11-09 r33 USB 时钟、键盘恢复与持续日志候选

r32 有线 USB 在旧内核上自行恢复，不视为新修复生效。当前内核证据确认
EUSB2 PHY 的 ref_clk_src 从未赋值，clk_get_rate(NULL) 得到 0。对照固定
LOS f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d 与 MiCode sheng
29db5d592c5b577aa9d9611da988a5e071d100dd，恢复原本必需的时钟获取和
包括 EPROBE_DEFER 的失败传播；不猜测频率。独立重放脚本与补丁、前后
哈希见 kernel618-usb-refclock-source.json。SS PHY set_parent 告警未宣称修复。

键盘旧日志在 643 秒 resume 时重新请求 MCU_Upgrade.bin 返回 EAGAIN，
传输停留 not ready；框架仍报告 connected。r33 保留首次 request_firmware
通过原厂 ueventd 找到 /odm/firmware 的路径，缓存固件到传输最后释放，
resume 复用缓存并延迟 100ms 调度，恢复被 suspend 取消的 12 秒保活，
MCU RAM 重置后恢复已连接触控板设置。固件仅下载 RAM，不刷配件存储。
ENOENT/EAGAIN 最多重试 60 次；未宣称实体输入和长期休眠恢复已通过。
不可读 HID 描述符现记 unknown，不能将 SELinux 拒读当成描述符缺失。

正常日志此前 120 秒关闭目标并释放缓冲，现改为前 120 秒每 250ms、之后
每 10 秒持续双槽记录，保留晚发异常入口与普通 panic 抓取；没有自动重启。
QEMU 实际 GPT/块 I/O、CRC 双槽、破损副本检测、125 秒额外延迟后的 BUG
调用栈及普通 panic 均通过；末次 137985ms。该测试不证明实机 UFS 或硬锁死
一定能落盘。报告 kernel618-hardware-r33-qemu-late-fault.json 与
kernel618-hardware-r33-qemu-direct-panic.json。

按用户要求实际重编内核和全部 344 个模块，统一 release 为
6.18.32-peiyuesheng-sheng-kernel、peiyuesheng@MiFans。EVA 使用实际
5.15 FastRPC 提供者的头文件与 Module.symvers 重编，未改二进制 CRC。
20957 项版本化导入、18008 项内核导出、归档执行权限与原厂 boot 解包回读
通过。Image SHA256=26f3bf8b25723631542027edcf5a43e50d6ac60e70df51e598876bd705edaec5；
boot SHA256=58455657cd0bf08f8605b81e78f5af0915d975a0eec3259f6a007ade759a373a。
07:11 已仅刷入 boot_a；无自动重启。初次 180 秒有线 ADB 检测超时；用户
确认系统正常运行。07:17 通过 WLAN 上的 mDNS 查询重新发现已配对设备端口，
无需重新配对，确认实际 release 与 boot_completed=1。原控制超时记录保留。
当前 bugreport 的真实 KERNEL LOG 确认 ref_clk_freq:0 已消失，PHY 重复器
初始化返回 OK，但用户和 dumpsys usb 均确认尚未连接，SS PHY 的 pipe_clk
set_parent 仍报错。不能将零频率告警消失当成 USB 已修复。
键盘 MCU 21.53 秒就绪，原厂 HAL 有真实固件版本回复；物理输入与休眠恢复
未验收。采样 CPU 三簇均为 performance，桌面累计1129帧、25次deadline
miss（2.21%），P90=36ms、P99=129ms；不是可比较的优化效果测试。
FastRPC lpass 会话返回 EUSERS 并伴随监听线程反复恢复，根因继续排查。
见 kernel618-hardware-r33-followup.json。

用户补充：卡的是相机录像，拍照可用；开机白闪后黑屏、运行卡顿、充电音效
卡顿仍在排查。新增 capture_sheng618_performance.py，只读收集 CPU/GPU
调频、热状态、负载及帧数据，不预设提频或关闭温控。白闪和录像本轮未改动。

## 2026-11-09 r32 后续启动确认与崩溃日志读回

初次检测的 180 秒 ADB 超时记录保留，但后续 06:10 已通过 ADB 确认仍运行
6.18 且 Android 启动完成，不能再把该超时等同于无法启动。06:19 经临时
Recovery 读取 run=9090d66d828ac02d，两槽身份和 CRC 有效。实测 msm_drm
初始化从 r31 的 13959ms 降为 1350ms，240 项模块批次从 28.041 秒降为
12.189 秒，首次非零双背光为 38.611/38.613 秒。尚未量化完整开机时间。
证据见 kernel618-hardware-r32-automation.json 与 kernel618-hardware-r32-progress.json。

用户报告随后一次崩溃并手动进入 Fastboot。本轮 06:31 校验 sheng、a 槽、
unlocked 与已验证 Recovery 哈希后，仅用 fastboot boot 临时启动 Recovery。
新建独立目录保存 rawdump，未覆盖 06:19 的记录；新 run=66c06b6a58ad0988，
两槽序号 384/385、时间 120139/120417ms，版本和 CRC 均有效。
其中 32.072 秒有 GPU 缺少 DDR 通道配置告警，33.798 秒起有六次 Wi-Fi
dp_rx_tm_deinit → __netif_napi_del_locked 告警。后者对应 ACK net/core/dev.c
7604 行的 NAPI 删除前状态检查。这些记录后日志仍继续，未抓到本次最终
Oops/panic，不能凭启动告警判定最后崩溃原因。

Recovery 中 pstore 为空，last_kmsg 不存在。rescue 以 ro,noload 挂载，logfs
以 ro 挂载，读后均已卸载；android-kmsg.txt 属于 modules-r14/crypto-r15 的
enablefilecrypto_failed 历史记录，oops 分区出现的是 5.15 内核记录，未找到
本次 r32 崩溃栈。未挂载 userdata，未执行格式化或分区刷写。设备留在 Recovery。
完整哈希和读回限制见 kernel618-hardware-r32-crash-readback.json。

源码确认正常构建的 sheng_bootlog 在 120 秒后关闭 destination 并释放 snapshot，
之后异常入口也因 destination 为空直接返回。因此晚发异常无法由现有记录器
落盘，下一轮需补持续低频记录与晚发异常抓取，同时保持自动重启关闭；本轮
尚未修改记录器、构建或刷入新镜像。

用户已验收拍照；录像卡死、实体键盘/触控板及插电音频卡顿仍未修复。
此前 bugreport 还显示键盘 resume 固件请求返回 EAGAIN，暂存的固件缓存和重试
候选尚未封包/实机验证，不作为已修复。物理输入抓取与用户操作时间未可靠
同步，不能声称已证明无事件。下次构建需按用户要求改为
6.18.32-peiyuesheng-sheng-kernel，并真实重编全部配套模块；尚未完成。

### r32 初次检测记录（已被上述后续证据补充）

核对 r8 生成器及固定上游/LOS 对照来源，确认 sheng_probe_checkpoint 内
350ms 和 CRTC 循环两处 350ms 均为本项目加入的诊断等待。新增可重放脚本
patch_sheng618_display_latency.py，仅去掉这三处等待，保留所有检查点输出，
没有修改面板 reset、电源或其他硬件时序。生成独立补丁、不可变修改前副本及
前后哈希；封包工具验证该来源链。清理后实际是否需要修正初始化顺序仍待日志。

同轮为 nanosic 主传输补上原厂 HID_ConsumerReportDescriptor（report 0x06），
从固定哈希原厂模块的 .data+0xb1a 提取25字节描述符，转发媒体/亮度键报告，
未猜测键值。新增实机描述符读取核验，但此轮未收到 ADB，尚未执行成功；
不将编译或描述符存在于源码当作实体媒体键通过。

display/keyboard 两组模块编译通过；344模块20966项版本化导入、18008内核
导出不变、归档权限、原厂 boot 模板/AVB/解包回读通过。相关 Python 语法检查
通过。03:03:46+0800仅刷boot_a，未启用自动重启。03:06:48启动检测以
180秒超时失败，期间没有收到ADB，当时Fastboot亦不可见。该结果仅描述
初次检测窗口；后续启动确认和读回结果见上文。

Image SHA256=80be4ce96640526d9ef5c2e66c76a0dd3cd6561b389ededaec5f90f7f82a3c48，
boot SHA256=955e8f7b9a57683fb66aba4e1c69e56c584c4025954f079ccec432de90a4bf43。
artifacts/sheng-6.18-hardware-r32 保留为可启动但仍存在功能和稳定性问题的
调试版本。原厂包未写入，没有备份当前boot。本轮崩溃排查未交付新版本。

NFC继续沿用原厂DT、实机与小米官方网页的联合结论：功能描述是NFC标签触发
分享，没有发现应补的主动控制器。未增加虚假设备绑定；碰一碰及跨设备传输
仍需另一台兼容设备验收，见kernel618-nfc-audit.json。

## 2026-11-09 r31 双背光接管与启动耗时定位

r31仅增加精确sheng板型的KTZ probe关灯及寄存器回读，保留LCD偏压，正常
亮度提交重新点亮。实际13.340/13.355秒，两颗亮度均0、enable=0x3f，接管前
均0x7f；53.258秒正常设置后两颗actual=2047、enable=0x7f、write_rc=0。
早期关灯与恢复已通过硬件寄存器验证，视觉白闪仍需用户验收。
高低亮度测试已恢复原始设置；原厂SELinux不允许shell直接读取寄存器属性，
实际回读来自前120秒内核记录，没有放宽权限。

344模块20966项版本化导入及18008内核导出、归档和官方boot封包检查通过。
02:53:09+0800仅刷boot_a，61.41秒连接ADB、68.57秒系统完成，无自动重启。
键盘/HAL真实通信和输入注册复查通过。rawdump run=e3165fec9c4df2a1，
末次120641ms，两槽身份和CRC有效。
Image SHA256=35cd333db3d4900484d942c1eba8e5fe60ac7c62e890f34e4c56a7df546a4f5e，
boot SHA256=3a43317d1fc43eec639eb084637de959070acb4c10c17914b1f6a2cff4973a6b。

本次保留了完整模块时序：240项串行装载从1.108到29.150秒，合计28.041秒；
msm_drm自身13.959秒，明显异常。源码核对发现r8诊断检查点的350ms等待仍被
沿用，包括6个CRTC各两次等待。接下来移除这些人为诊断停顿，保留板级硬件
时序与非阻塞检查点输出；不把尚未制作的修正写成已缩短开机。
详见kernel618-hardware-r31-progress.json。

## 2026-11-09 r30 键盘 MCU 与原厂服务通信

新增 nanosic_driver 原生模块，344 模块20965项版本化导入及18008内核导出
一致性通过，归档权限、官方 boot 封包/AVB/解包检查通过。02:43:38+0800仅刷
boot_a；59.50秒收到6.18 ADB，64.98秒系统完成。无自动重启，最多五版。
Image SHA256=5c063f7911e3632f4cecd36b52bc4fd79f8f376688c3ba635817deeea9acce42，
boot SHA256=ed1cdf1961e55b5950191842595e812f215936fec6d492effb6b1657f985f90f。

源自 map220v/sm8550-mainline 固定提交 f273227fab85e2ad8391c61c21b3556bd017a726
的 sheng WN8030 实现，保留GPL声明。MiCode sheng只公开charger companion，
LOS nuwa没有本机MCU传输。对照原厂DT、模块反汇编和nanoapp服务，适配GPIO
属性及极性、三路原厂电源、66字节命令写入和去掉3字节包头的vendor报告读取。
接口是原厂实际打开的/dev/nanodev0；没有采用参考实现的独立认证daemon接口，
认证消息原样交给原厂HAL。增加有界队列、文件生命周期、固件边界检查及异步
等待原厂/odm挂载。只下载既有MCU固件到RAM，没有替换或刷写键盘升级文件。

实机27.91秒注册主传输，35.39秒MCU RAM固件就绪；前几次ENOENT后重试恢复。
原厂SELinux标签nano_device及init权限已自然生效。nanoapp正常运行，真实读取
MCUVersion=XM_N81A-125-1107、keyboardVersion=0141、TouchPadVersion=0e9c，
connect/enable均true。Android已注册Xiaomi Keyboard和Xiaomi Touchpad输入；
mIdentityPass=true仅记录框架状态，不单独视为完成认证流程的证明。
没有注入按键，也没有替用户确认物理按键/指针效果。

rawdump两槽身份/CRC有效，run=a73ad38fc4b5c247，末次120549ms。
首次读取发生在ADB退出、Fastboot尚未枚举的窗口，重试后读回成功；控制记录保留。
原厂第二阶段加载器仍会因未移植的nanosic_platform依赖报告旧模块加载失败，
这不推翻已运行的主传输；charger注入、电量/充电、边缘过滤及额外HID报告尚待补全。
键盘实体输入、拔插和休眠验收留待用户醒后，不宣称配件完整无故障。
源码与运行核验见kernel618-keyboard-source.json、kernel618-hardware-r30-keyboard.json。

## 2026-11-09 r29 原厂相机预览与面板复位候选

r29 已刷 boot_a 并正常启动；59.26 秒连接实际 6.18 ADB，64.58 秒记录系统
启动完成。343 模块的 ABI、18008 内核导出、归档权限、AVB 及官方模板解包
回读通过。无自动重启，只保留最近五版。Image SHA256 为
8629d4b96da60130703e39f9278c06119ae07a998948d80095470ff630852af0，
boot SHA256 为 ce29881996542803134b795c80c91c1988cc865982cd371bc69b04d175d72e4a。
rawdump 两槽版本/run 和 CRC 有效，run=069f91c3f89220e0，末次120549ms。

修正此前相机测试的判断：原厂相机先前没有真正打开，是安全 intent 仍停在
滑动锁屏。确认系统明确报告 secure=false 后，使用系统正常的 dismiss-keyguard
和原厂相机普通 intent，不处理或绕过任何凭据。原厂后摄 SurfaceTexture
1920x1440 预览帧连续为67→142→217→292，前摄为47→99→151→203，均有
同步 YUV 流。前后摄原厂 App 预览链路已实际输出，不能再按“相机完全不可用”
记录。没有拍照或保存像素，拍照、录像和视觉效果仍待验收。测试后用普通相机
intent 恢复后摄并返回桌面。

原生 shell Camera2 测试仍在另一条缓冲路径返回0帧并引发 provider 恢复；
这一限制单独保留，不能用它推翻原厂 App 已确认的预览帧进展。详细证据见
kernel618-hardware-r29-stock-camera-0/1.json 和 camera-1-private-frames.json。

面板复位候选在 N81A 的物理 reset 前将双 KTZ LED 亮度清零，保留 LCD 偏压，
再由正常提交恢复亮度。此轮早期日志未确认 continuous splash 是否执行此
reset 路径，且没有视觉验收，不能宣称白闪已消失。实际亮度寄存器回读仍与
写入一致。整体开机时间仍约65秒，继续排查。

指纹 HAL 无死亡、霍尔输入节点已注册、Wi-Fi 实际连接和数据传输正常；
指纹录入/匹配、实物合盖、亮度视觉效果和充电音效需实际操作验收。
键盘/触摸板主传输模块仍待移植，不将 charger companion 当作完整驱动。
NFC 审计结论见下一节：官方描述为标签触发分享，未找到应补的主动控制器。

## r27/r28 触摸早期固件与亮度回读

r27 增加有上限的128KiB早期驱动记录，并保留原来的最新日志尾部、版本/run
身份及 CRC。AArch64 QEMU 实际写 GPT/fsync、两槽 CRC、破损副本拒绝、日志
回卷后早期标记仍在的断言通过。没有扩大 rawdump 写入范围，也没有自动重启。
实机两槽读回有效：r27 run=f343b01b79c6830f，末次120612ms。

早期记录确认触摸在27.96秒探测，31.20秒请求本机固件时连续返回ENOENT，
原厂/vendor尚未就绪，原实现放弃启动下载。r28只在ENOENT时每秒异步重试，
上限60次；其他错误不隐瞒，CRC、固件头及帧检查保留，失败时不再发笔命令。
r28实际第一次请求31.21秒失败，第二轮32.38秒请求后33.27秒成功下载，
33.44秒完成，早于51秒首帧亮度设置。不再依赖之后的熄屏/亮屏触发下载。
70.24..70.60秒的唤醒流程约352ms；尚待用户复核手感及长期休眠。

r28双KTZ8866实际I2C回读与写入一致，包含开灯、熄灯、低/高亮度变化：
requested=307对应actual=1314，requested=1213对应actual=1779，
requested=0对应actual=0/enable=0x3f，两颗write_rc均0。
因此背光调节已通过硬件寄存器链路验证；视觉效果待用户确认。
只读sysfs遥测受原厂SELinux限制，未修改enforcing或策略；改用限频且仅前120秒
的内核寄存器记录。r28亮度测试已恢复原亮度设置和自动模式。

r28实际6.18 ADB为59.27秒，系统完成记录65.33秒，整体开机时间尚未明显缩短。
run=29401ccbe62ef88a，末次120494ms，版本身份与两槽CRC有效。
boot SHA256=4177b508c540e22c8f0cde440396187cc1f58d1f7563447fdc27341dce6058af，
Image SHA256=6d5f4c1490b4532066696e78bb8cf7ab663c137106f2c64bf97d2f0190e339b4。

新增原生Camera2测试仅丢弃RAM图像，不读取像素、不保存照片。
r28后摄open/session/repeating均返回0，但0帧/0完成回调，之后原厂provider重启。
日志显示IPE输出buffer获取失败，不能声称预览已恢复；前摄因provider变化尚未实际打开。
内核/供应商请求链与缓冲分配继续调查；原厂相机App实际预览仍待验收。

NFC已取得小米官方规格/功能页，明确写Supports NFC tag，说明手机碰平板NFC区域
触发Xiaomi Share传输。结合原厂DT及实机无主动控制器/服务/feature，当前没有应补的
主动NFC读写控制器绑定。来源网页快照哈希及DT检索见kernel618-nfc-audit.json。
标签触发与实际跨设备传输需要另一台兼容手机验收。

后续仍包括开机白闪、整体开机时间、相机图像链路、插电音效、键盘/触摸板。
实体合盖和指纹录入/识别需用户醒后测试。r29正在制作面板复位前关闭LED的候选，
只保持LCD偏压，是否消除白闪尚未验证。

## 2026-11-09 r26 指纹与霍尔

r26 新增 fpc1552、xiaomifp、xiaomi_hall 三个原生模块，合计 343 个。
FPC 来源为 MiCode sheng 固定提交 29db5d592c5b577aa9d9611da988a5e071d100dd；
保留原厂 HAL/TEE 和 sysfs 协议，适配 6.18 GPIO、remove、面板通知 API，
补 GPIO 所有权、唤醒源及卸载清理，并移除原公开源码中未初始化 work 的调度。
没有修改指纹匹配或录入逻辑。

霍尔依据实际 DT 的 GPIO171/172、EV_SW 及四路 ADSP SMP2P 开合中断报告输入；
原厂模块反汇编确认开合极性和 IRQF_TRIGGER_RISING|IRQF_ONESHOT。
未发现可直接复用的 sheng 公开实现；未实现原厂私有字符设备算法控制。

343 模块 20889 项版本化导入、18008 内核导出一致性、cpio 权限、AVB 与
官方 boot 模板解包回读通过。01:58:32+0800 刷 boot_a，59.39 秒收到实际
6.18 ADB，64.83 秒记录系统启动完成。三个平台节点均绑定；指纹框架空闲且
HAL deaths=0，r25 的 HIDL daemon is null 忙重试消失。Android 已识别
xiaomi_hall 输入设备和两种开关。实物合盖、指纹录入/识别尚未验收。

boot SHA256=107b2a7d0b57e34d4ad876d79d228f7504d141a8af009c65e3cae9adf55af90b，
Image SHA256=e6a712f4aa2929626872b7aebbf68d59ad31c72cf8a71f5c0237b046560248c0。
交付 artifacts/sheng-6.18-hardware-r26/，无自动重启，最多五版。
核验索引 kernel618-hardware-r26-switches.json，源文件哈希分别见 fingerprint/hall-source。

r25 日志读回成功，run=0ab7429b895f0772，末次 uptime=120485ms；
版本身份与两槽 CRC 有效。早于33.6秒的日志已被挤出，不能据此判断早期触摸固件加载。

NFC：r26 没有 NFC 系统服务或 hardware feature，没有控制器设备节点；实际 DT
暂未发现启用的 NFC 控制器，只有通用 pinctrl 名称。通用厂商配置或加载 nxp/stm
模块不能证明本机存在对应控制器。尚未取得官方资料确认，不制造虚假绑定。
触摸唤醒慢、开机白闪/慢、插电音效卡顿、键盘仍在继续排查。

## 2026-11-09 r21 结果与 r22 触摸修复

r21 在 57.34 秒收到实际 6.18 ADB，65.22 秒完成 Android 启动。
原厂系统和强制 SELinux 保持；无测试超时、无自动重启。

用户确认触摸、手写笔仍不可用，并报告扬声器间歇卡顿。
不能把 `/dev/xiaomi-touch` 出现或模块注册当作触摸恢复。
`spi0.0` 没有绑定驱动，NVT 触摸和笔输入均未出现。

只读原厂设备树的 novatek@0 列出 panel=<0x747 0x74e 0x74f>。
0x747 为通用 Visionox 节点，无 sheng 的 mi,panel-id；后两项才是
N81A，ID=0x4e38316150360200。r21 移植新增的保护只检查第一个
phandle，提前返回 ENODEV。r22 改为遍历该触摸节点的完整 panel 列表，
只接受可用且 ID 精确匹配的 N81A，并记录命中的索引或拒绝原因。
保留 sheng 固件名、SPI/笔功能及板级范围限制。

来源已在 kernel618-touch-source.json 固定 MiCode piano-w-oss 提交
6957f6b646d1c919e175e6f9000eb50c8635273c；它提供同一 NT36532 THP
和笔协议实现，但其面板列表与 sheng 不同，不能照搬首项假设。
nuwa/通用 SM8550 底座没有 sheng 的这组 THP 绑定；以本机原厂 DT 为准。

r21 六颗 CS35L43 已在 secondary TDM RX/TX 链接，六颗均有固件加载记录。
这不证明连续播放正常：AudioFlinger 抓到 fast mixer underruns=105、
overruns=972，logcat 记录 AudioOut_D 一轮 65.66ms，预期 20ms。
暂未确认瓶颈在调度、PCM/DSP 还是其他路径，不先修改缓冲或功放时钟。
原始日志在 reports/device/kernel618-peripherals-r21/；整理哈希与结果见
kernel618-peripherals-r21-hardware.json。

r21 日志已通过临时启动已验证 Recovery 读取：run=dd9aec1354313193，
CRC 有效两份，末次 uptime=120601ms，已返回 Fastboot。
第一次 ADB reboot 调用超时但设备实际进入 Fastboot；第二次从 Fastboot
完成读回，失败记录保留。

r22 编译、340 模块的 20785 项版本化导入、18008 内核导出、
cpio 权限、官方 boot 模板封包/AVB/解包回读均通过。
与 r21 相比只替换两份触摸模块，未改音频；实际触摸/笔效果待验证。
新增直接构建外围模块脚本，避免上游手机补丁重放覆盖已适配源码。
普通测试脚本刷写前会有界等待 Fastboot 枚举。

## r22 实机与 r23 ABI 修正

r22 已实际绑定 spi0.0，注册 NVTCapacitiveTouchScreen、M80p 和 P81c，
Android/ADB 正常启动，但用户实测触摸和笔仍完全无响应。
读回发现 xiaomi_touch_dev_read 持续报 `error count 520 to read, need 1032`。
原厂驱动反汇编 xiaomi_touch_dev_read:0x3354 比较 0x208（520），
MiCode piano 新版 common_data_t 的 data_buf 却有 256 个 s32，结构为 1032 字节。
这是移植源码与本机 HyperOS 的另一处确定 ABI 差异。

r23 将公共命令恢复为 128 个 s32（结构含头共 520 字节），在编译时断言
common_data_t=520、hardware_param_t=214，并限制生产者写入长度，防止越界。
尚不能仅凭这处修复认定原厂 THP 的其他协议均兼容，继续实机验证。

r22 两份 rawdump 快照 CRC 有效，run=eb423662157b76ca，sequence=395/396，
uptime=120310/120600ms。巨量重试日志挤出了周期版本身份，自动工具按原规则
拒绝认领，未放宽校验。原始 region-after.bin 和失败记录保留；上述错误由受控
r22 刷写与此次唯一运行关联，不能声称快照带有 r22 身份。已手动从临时 Recovery
返回 Fastboot。r23 同时给每份快照尾部保留 CRC 覆盖的版本/run 身份，避免日志
风暴再次挤掉身份；槽位格式、分区校验和写入范围保持原值。

r21/r22 的音频卡顿尚未修复；触摸服务反复读取失败可能增加负载，仅列为待验证
因素，不把它写成已确认的音频根因。

## r23 实机与 r24 帧长度修正

r23 59.66 秒连上实际 6.18 ADB，67.04 秒记录系统启动完成。
原厂 HAL 的 common 命令已经正常处理，不再因 520/1032 差异忙重试。
用户实测触摸仍不可用；不得把中间接口修好当作触摸功能恢复。
119.66 秒的 /proc/interrupts 显示 xiaomi_tp 已有 1201 次中断。
内核却持续丢弃 crc_len=0x4bb 的包；包内校验字段与各自反码一致，
失败来自源码硬编码只接受 piano 的 0x4c3/0x50d。

只读原厂 nt36532_touch.ko 反汇编 nvt_ts_work_func：0x9664 比较 0x505，
0x966c 比较 0x4bb，0x9674..0x9684 保留 checksum/length 反码检查。
r24 精确恢复 sheng 的这两个长度，不扩大接收任意长度，不跳过校验，
不替换原厂固件。r23 在 70.193 秒成功装入本机 n81a CSOT 固件，
FW=0x13、PID=0x5981，frame_len=5160；并非固件不存在或 SPI 无数据。

r23 rawdump 自动读回并返回 Fastboot 成功，run=836f66062bced21a，
末次 uptime=120578ms，版本/run 尾标记与快照 CRC 有效。
同一 r23 Image 的 AArch64 QEMU 实际 GPT 写入/fsync、双槽 CRC、
破损副本拒绝、命令行被挤出后身份尾标记均通过。
只跑了此次变更相关正例/回卷测试，未重跑既有分区名称/大小拒写测试。

r24 编译、340 模块 ABI、18008 导出、原厂 boot 封包解包检查通过。
boot SHA256=805aab1554cc394c6d1d41a87c160c000910e5a45eab1e5c71ed97150ddb5759，
Image SHA256=ef45268d3995d2be3991e3b53d3c508c124898c42f813e67ab3b4cb3a2d1ed32。
已刷 boot_a，实际触摸和笔验证仍在进行，音频卡顿未宣布修复。
交付目录最多五版，正常版本均未启用自动重启。

## r24 用户确认触摸、笔恢复

r24 59.28 秒连上 ADB，65.03 秒记录 Android 启动完成。
用户明确反馈“都可以了就是触摸启动的有点慢”。记录为手指点击、笔落笔
基本功能已由用户验收；压力/倾斜/按键、休眠唤醒与长期稳定性尚未完整验证。
实际 dumpsys input 已有手指坐标变化，getevent 也记录到手指输入。
25 秒监测窗口中未记录到两支笔设备的事件，不据此推翻用户实测，也不虚报
已抓到笔的完整坐标轨迹。

仍有触摸启动慢、开机白闪、键盘/触摸板等未完成问题。
r24 THP HAL 偶有 `copy_frame_data_from_mmap:err tp_frame crc error`，
暂未区分环形缓冲并发读取或其他原因，不能把基本可用写成完整无故障。
扬声器需持续播放复测；准备抓取时 ADB/Fastboot 均不可见，已询问 USB
连接情况，尚不能归因 USB 驱动或断线。没有因此开启自动重启。

## 2026-11-09 r25 相机电源 ABI 与双背光

r24 用户进一步确认连续音乐不再卡顿，但插电音效及同时播放的音乐会卡一下。
USB 消失由用户确认是手动拔线，已重新接回，不记为 USB 故障。
新反馈包括亮度条完全不改变屏幕亮度、相机不可用、合盖开盖无反应、
指纹不可用、触摸唤醒慢；开机慢、白闪及键盘/触摸板继续保留为待修。
用户已要求夜间自行推进，暂不询问；需要物理操作的验收留待用户醒来。

r24 rawdump 成功读回，run=ba7fdf6b1024666d，末次 uptime=120416ms，
版本/run 尾标记及 CRC 有效。相机反复拒绝 `Invalid Seq type: 14`，
三个本机传感器及 EEPROM 的上电因此失败。MiCode sheng 和 LOS nuwa
均定义 SENSOR_BOB=13、SENSOR_BOB2=14；选用的通用驱动却将 13 定义为
CUSTOM_REG3，最大值为 14。r25 恢复 BOB/BOB2 的原厂编号与 cam_bob/
cam_bob2 电源映射，同时保留通用 CUSTOM_REG3 在后续编号及原有电压验证。
没有更换相机固件或跳过上电失败。

N81A 原厂 DT 采用 bl_ctrl_external，两个 ktz,ktz8866 节点分别位于
I2C 0/4、地址 0x11。通用驱动的 DSI_BACKLIGHT_EXTERNAL 分支为空。
r25 接入 MiCode sheng 的 2048 项亮度映射及原厂偏置/LED 控制寄存器，
只在精确 N81A 面板使用，补 6.18 I2C API、列表锁/注销及错误传播。
先写亮度再使能 LED，避免使能时短暂使用旧亮度；此项尚不能证明白闪已消失。
来源、固定提交、适用差异及完整补丁见 kernel618-camera-backlight-source.json
和 sheng-camera-backlight.patch。

r25 340 模块 ABI、18008 内核导出、cpio 权限、原厂 boot 封包解包检查通过；
只刷 boot_a，无自动重启。59.27 秒连接真实 6.18 ADB，67.00 秒记录启动完成。
boot SHA256=7bdfa23ffa90e0990ff26feebe460b2bd1b3237c4abcf7b2b610c34bce4e06fc；
Image SHA256=5f189e7d3bc81607d693eb411cb90e24497444303067cd86a71dfbbc8aa35c13。
实机两个 KTZ8866 均已绑定；相机 HAL 从 0 恢复为 9 个逻辑设备，4 个公开设备。
这不是九个物理摄像头，也不等于拍照/录像通过。安全相机 intent 测试未打开
实际相机客户端，设备仍在锁屏，未绕过锁屏；预览验收仍待完成。
亮度控制的物理效果仍需验收，不因驱动绑定就标为完成。

诊断目录 reports/device/kernel618-hardware-r25/services-1794159999865978940/
及 preview-1794160049233457332/；相机设备列表较大，原始日志不入 Git。
新增有界只读服务/音频采集脚本及不拍照的预览测试脚本。
指纹 FPC 与霍尔的下一版源码准备仍在继续，未混入 r25 实机结果。

# sheng 音频继续调试：2026-11-06

最新结果见 reports/AUDIO_OFFLOAD_STATUS.md：压缩卸载 r1 已固化并重启验证，用户确认六个扬声器和音量正常、卸载左右声道方向正确；PCM 保留，Dolby 关闭。下面为历次定位记录。

## 已确认的反馈和证据

- 用户确认基础 r2 的平板布局、触摸和自动旋转正常；前灯已熄灭。
- 铃声能从六个扬声器大声发声。媒体最初只有左侧微弱；临时禁止压缩卸载后左侧音量变大，右侧仍无声，音质偏刺耳。
- 原机 ODM 的 Dolby tuning 为四通道；vendor 的通用 fallback 为两通道。临时将 ODM 文件覆盖 vendor 路径并重启 DMS/音频后，用户更正反馈为“仍只有左侧，音质似乎改善”。这不是双侧输出已恢复的证据，也不能单凭此认定原先未加载 ODM 文件。
- libdlbdsservice.so 同时包含 ODM 和 vendor tuning 路径。
- 暂时删除媒体的 dlb_music_listener 后，用户仍报告仅左侧发声；已撤回 XML 挂载。保留该监听器的原厂配置。
- 双声道到四通道 MFC 的旧诊断库曾临时加载，日志确认使用 FL/FR/FL/FR；用户确认完全无声。该重复 channel ID 方案已关闭，源代码精确撤回，未纳入镜像，旧脚本已禁止运行。
- 关键故障已取证：hal_audio_default 调用 hal_sheng_dolby_default 被 SELinux 拒绝 `{ call }`。同时 libhwdap 反复记录 `Connect to Dolby Native Service failed`，GEF DAP 模块设置返回 -EINVAL。仅创建/启用 AudioEffect 不能说明原厂 DSP 参数已生效。

## 正在固化和验证的修复

- 增加 Dolby HAL client/server 的必要 Binder 通信及 callback 权限，保留 SELinux Enforcing。
- 策略编译和完整 CIL 编译通过，vendor 镜像内容/属主回读、分区大小、AVB 签名及完整 vbmeta_system 链检查通过。
- vendor_b/odm_b/vbmeta_b 已针对 ca10ede3 / sheng / b 槽成功刷写。用户随后确认停在 AVB 页面，短按电源后进入系统；ADB root、boot_completed=1、Enforcing 已验证。音频服务正常运行，Dolby Binder call 拒绝及连接失败消失，但卸载音乐仍完全无声。AVB 页面原因尚未核对，不能推断 USB 被拔掉。
- 源文件、原机 mixer/resource 配置已同步到独立 WSL 设备树，并逐文件验证一致。

## 当前优先级：无 Dolby 的基础六扬声器

- 用户明确要求先修默认六扬声器，暂停 Dolby 和相机调试。
- Dolby enabled=false 已写入 prefs，并结束其旧应用进程；当前临时 audio_effects bind mount 去掉媒体 dlb_music_listener，保留 Qualcomm music_helper。audio.offload.disable=1、audio.deep_buffer.media=false；均未固化为镜像修复。
- 重新播放后用户确认仍只有左侧。AudioFlinger 活动音乐轨道为双声道、左右音量均 0 dB、balance=0，自动效果只剩 Qualcomm Volume listener for Music；六组功放为 On，ASPRX1 slot 仍是原厂 2/2/0/3/3/1。
- 独立编译并临时加载合法 FL/FR/LB/RB channel map 下的 2→4 混音系数库。用 PARAM_ID_CHMIXER_COEFF、Q14 unity、56 字节对齐 payload；仅 sheng 的 TDM speaker PCM stereo 路径生效，不增加功放增益。用户确认两侧恢复，随后确认六个扬声器正常出声。
- SPF 官方 AudioReach chmixer_common_api.h 明确系数为输出行、输入列；旧 PAL 的对称 2×2 swap 注释不能用于判断非方阵顺序。当前矩阵为输出 slot 0/1←L、slot 2/3←R：`[0x4000,0, 0x4000,0, 0,0x4000, 0,0x4000]`。用户通过隔离低频左声道/高频右声道 PCM 测试确认低音左、高音右，实际立体声方向正确。
- 音乐曾短暂无声，日志显示播放器进度停在约 49.8 秒、AudioFlinger 因断粮移除 track；音频服务未崩溃。用户重播后恢复。113 秒本地纯 PCM 探针连续段的进度和播放时钟正常，90 秒中间报告 underruns=0；最后主动停止前排空时计数为 1。测试结束后主动停声，随后已恢复音乐，用户再次确认六扬声器正常。不能据此宣称所有播放器/编码的间歇故障已排除。
- 持久修复镜像位于 artifacts/system-audio-pcm-sheng-r1/，只改 vendor 中 libar-pal.so、两份 audio_effects.xml 和三个默认属性。保留原厂功放保护、增益和 mixer/resource。原机 Dolby prefs 保持关闭，媒体自动 dlb listener 不再附加；默认禁止尚未工作的压缩卸载。与当前 ODM 字节一致的引用校验通过，仅刷 vendor_b/vbmeta_b，重启验证进行中。

## 构建和 AVB 补充

- 新 vendor SHA256：7762d270cee1aad7d24d7d4589df8005c8bc77f49d29994e15d90a4904a54bd8；vbmeta SHA256：6aaa327d19de9704c9b0aec8cf9bf02e5c33febf9d0cd03c3ffd795ee1043d5c。全量文件内容/属主/权限回读、分区大小、签名和原始 chain descriptors 检查通过。
- 基础 r2 的实机 vendor/odm 分区哈希与镜像一致；vbmeta 实际块设备为 131072 字节，前 8192 字节哈希与已刷镜像一致。先前整块哈希不同来自分区尾部，不能直接据此认为 vbmeta 被篡改。当前 verifiedbootstate=orange，AVB 提示页原因尚未最终确认。
- 第一轮打包回读发现旧 OTA 文件清单遗漏后来加入的 THP 服务，未刷写；已修正为保留当前基线全部文件，新一轮全量回读通过。失败目录保留为 system-audio-pcm-r1-failed-filter。

## PCM 持久性修正：r2

- PCM r1 已刷入、boot_completed=1，库和 stereo_quad_coeff=true 重启后有效，但 audio.offload.disable 在 vendor/build.prop 中未被系统加载（读取为空）。音乐重新选择 compressed_offload，用户报告只有左侧微弱。r1 不能标记为六扬声器持久修复成功。
- 改为仅从 primary module 的 Speaker route 中移除 compressed_offload，保留其他设备和所有 mixPort。AudioPolicyManager 不再为内置扬声器选择压缩卸载，普通音乐自动回退 PCM。移除了无效的 vendor audio.offload.disable 属性。
- 临时挂载新策略、只重启 audioserver，在 audio.offload.disable 仍为空的情况下验证：policy dump 的 Speaker sources 不含 compressed_offload，音乐使用 48k/24bit stereo deep-buffer，合法 2→4 MFC payload 生效。用户最初报无声，随后更正为等待一两秒后六个都响。
- r2 只相对 r1 改 build.prop 和 sku_kalama/audio_policy_configuration.xml。vendor SHA256 c7b454eca8ef011c5ff3dc74003f2aff7f515df7667c85de4f29ec6f561ce5c4；vbmeta SHA256 95a9e99881f48a558da3180f1c2528cd926e30f710ea9e0192d70c39a8b90df9。全量内容/权限回读、原始分区大小、AVB 签名及全部其他 descriptor 保留检查通过。正在针对 vendor_b/vbmeta_b 刷写并重启。
- 用户询问 PCM/压缩卸载及是否可修：已说明先解码与芯片解码的区别；原厂支持压缩卸载，但当前故障仍未修复，优先完成默认六扬声器持久验证。

## r2 最终实机结果

- vendor_b/vbmeta_b 刷写完成，用户短按电源越过 AVB 页后进入系统；boot_completed=1、ADB root、SELinux Enforcing。
- 重启后库、策略、效果配置的 SHA256 与打包源一致；无 libar-pal/audio_effects/audio_policy 临时 bind mount。audio.offload.disable 为空，stereo_quad_coeff=true、deep_buffer.media=false，杜比 prefs=false。
- AudioPolicyManager 的来源是镜像中的 sku_kalama/audio_policy_configuration.xml，Speaker route 不含 compressed_offload；活动媒体为 48k/24bit PCM deep_buffer，MFC 正常发送双声道到四通道混音。
- 用户明确确认：**重启后六个扬声器都正常出声**。默认六扬声器出声及此前隔离左右测试通过；压缩卸载、Dolby 音质调校、全部播放器长期连续性仍未完成，不应据此宣称这些项目已修好。
- 刷写和启动证据：reports/device/system-bringup-r2-20261106-184936/。音频最终证据：system-bringup-r2-followup-20261106/pcm-r2-persistent-boot-state.txt、pcm-r2-persistent-policy.txt、pcm-r2-final-audio.txt、pcm-r2-final-partition-hashes.txt。

## 相机和启动显示的附带进展

- 相机的 vendor_ssgtzd/vendor_thermal 用户组修复已独立刷入并重启验证；服务带组 2907/2912，socket 未放宽权限，枚举 9 个设备、4 个公开设备。
- 相机仍在第一次预览时崩溃，明确堆栈为 libui 的 GraphicBuffer 析构，经 camera.xiaomi.so 的 GraBuffer/RemoteRequest；不能记为相机可用。
- 使用本次 vendor libui 的精确编译参数测得 sizeof(GraphicBuffer)=3376，而 OEM 封装四处仅分配 256。已生成四处 MOV immediate 修正版并验证其余字节完全一致，原始库和原厂固件未改变；文件在 artifacts/camera-graphicbuffer-sheng-r1/，尚未加载或刷入。
- 用户报告 Fastbootd 界面出现前有背光黑屏约 1–2 秒，安卓启动动画出现前约 1 秒。尚未完成启动显示时序定位。

所有新证据位于 `reports/device/system-bringup-r2-followup-20261106/`；未拍照、未打开电脑摄像头、未清除 userdata。

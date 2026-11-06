# sheng 系统实机状态（2026-11-06）

## 最新音频状态：压缩卸载 r1 已固化并通过重启验证

当前安装 artifacts/system-audio-offload-sheng-r1/ 的 vendor_b/vbmeta_b，ODM 未改。boot_completed=1、ADB root、SELinux Enforcing；无音频临时挂载。用户明确确认重启后“六个都正常，音量正常”，并确认卸载 stereo MP3 隔离测试“低音只在左，高音只在右”。

保留 PCM 回退；Speaker 默认允许 compressed_offload。PAL 解码后使用合法 2→4 混音，stereo 音量重置 master 后按原左右音量配置；mono MP3 请求 stereo 解码输出而不改变 encoded mono 输入。生产 PAL SHA256 c20ed5ddeb7b87d22e8a317f4ab5cae5bb41dc34b1f7ade84dfb0756752bf3de。默认 Dolby 仍关闭。

已验证 stereo MP3、mono MP3、stereo AAC，以及 mono 两遍播放/暂停/恢复；其余 codec/profile 和长期连续性未全面验证。详细记录 reports/AUDIO_OFFLOAD_STATUS.md，清单 reports/system-audio-offload-r1.json，最终证据 reports/device/system-bringup-r2-20261106-193529/。不得使用旧 PCM 打包脚本来重打卸载版本；单独脚本为 scripts/package_sheng_offload_audio.py。PCM r2 镜像保留作为已验证回退。

用户仍要求不拍照、不打开摄像头、不清 userdata、不整包重编、不启用子代理。当前卸载任务已完成；相机、144 Hz、双击亮屏和电源键动画尚未完成，杜比调校未继续。

## 以下为此前音频/系统修复记录

## 最新补充：已进入系统，优先修复无 Dolby 的基础六扬声器

**默认六扬声器已完成持久修复。** PCM 音频 r2 已刷入 vendor_b/vbmeta_b，重启后用户确认六个都正常出声。系统默认策略为内置 Speaker 选择 PCM，并使用合法四通道混音覆盖六组功放；无临时挂载、无需临时禁止卸载属性。左右隔离测试也已验证方向正确。杜比保持关闭，压缩卸载及音质调校尚未完成。最新镜像 artifacts/system-audio-pcm-sheng-r2/，证据 reports/device/system-bringup-r2-20261106-184936/。

- 新 vendor_b / odm_b / vbmeta_b 全部刷写成功。用户随后确认停在 AVB 页，短按电源后进入系统；当前 ADB root 正常、boot_completed=1、SELinux Enforcing。AVB 提示原因仍待核对。
- 新 vendor SHA256 a4f8d6aca18835ac05f589261b848cae672fbb5d071b84afffd4e8bf5f3b1052；odm SHA256 380aac5b18d5573a8389847553ffcdfdbbf8422413548daddd3389f5bcc76b6d；vbmeta SHA256 4f1f552165c28bf9216b6ee1238e40c121237607526fca67b4c3b7b819657e1d。
- 音频关键新证据是 hal_audio_default 调用 hal_sheng_dolby_default 的 Binder call 被拒绝，导致原机 DAP 不能连接 DMS。已添加限定 Dolby HAL client/server 的调用和回调规则，完整策略编译通过，仍使用 Enforcing。
- 新镜像中 Dolby Binder 拒绝及连接失败消失，卸载音乐仍完全无声。按用户要求已关闭 Dolby 并去掉媒体 dlb_music_listener，先修 PCM。合法四通道混音系数已临时验证：用户确认六扬声器出声，隔离左右测试音也确认立体声方向正确。音乐中途有一次断粮，重播恢复；本地 113 秒 PCM 测试正常，详见音频报告。只改 vendor/vbmeta 的持久修复镜像已打包，重启验证进行中。
- 相机组修复已在前一轮独立重启验证，无需改 socket 权限即可枚举 9 个设备、4 个公开设备；预览仍崩溃于 GraphicBuffer 析构。新定位表明 OEM 相机封装仅分配 256 字节，而当前 vendor libui 精确编译参数测得 sizeof(GraphicBuffer)=3376。已生成仅改四处 allocation immediate 的待测试库 artifacts/camera-graphicbuffer-sheng-r1/camera.xiaomi.so，未刷入。
- 原机 mixer/resource、触摸服务、IDC、相机 RC、属性及策略等 12 个目标源文件已同步到 WSL 并逐字节验证；无效的 gr_adreno_info.cpp 构造函数等待补丁已精确撤回，已生效的显示服务入口等待保留。
- 用户报告 Fastbootd 初显前有背光黑屏约 1–2 秒，安卓启动动画前约 1 秒，尚未完成显示启动时序定位。144 Hz、双击亮屏和左侧电源键动画仍待修复。

详细音频证据和操作记录见 reports/AUDIO_BRINGUP_FOLLOWUP.md。当前只处理基础六扬声器 PCM 路由，暂不穿插相机、刷新率或 Dolby 调校。

## 最新状态：r2 已刷入并通过布局/触摸/旋转实机验证

以下本节取代后面的历史状态。用户现要求不拍照；不得打开电脑摄像头。旧后台 worker PID 51152 已停止，不得重启旧 worker。

- 当前 ca10ede3 / sheng / b 槽，内核 5.15.220-gf9ca2b71f672，SELinux Enforcing。用户已授权针对性刷写、重启及 ADB 输入；保留 userdata。
- r2 vendor_b、odm_b、vbmeta_b 已在 Fastbootd 成功刷写，sys.boot_completed=1。完整 vbmeta_system 链已保留，签名/文件回读/分区大小验证通过。脚本最后的 dmesg 收集因 ADB root 设置未恢复而失败，不能误认为刷写失败；随后已恢复官方 ADB root 调试。
- 用户确认屏幕亮起、普通平板布局正常、触摸与自动旋转都正常。SystemUI 实际读取 internal desktop/support=false；input dump 识别 NVT IDC Rotation90；方向事件按 (rotation+3)%4 处理，当前姿态从 Rotation90 修正到 Rotation0。
- 原生 THP 处理服务已启动，PID 1339，domain vendor_sheng_touch_report；不是旧临时 su 进程。已使用独立最小策略，保持 Enforcing。
- 实际显示服务入口等待 KGSL 后再构造 allocator/composer。实测重启后 allocator maps 已含 libadreno_utils.so；当前 activeMode=60，HWC cur=60，idle_time/inactive=0。旧 gr_adreno_info.cpp 构造函数补丁并未改变实际预置库，不能算部署。
- 144 Hz 尚未适配：用户选择 144 后卡死、息屏无法再点亮；通过 ADB 退回 min/peak=60 并重启显示链路后恢复。不要宣称 144 正常或任意提高内核时钟。
- 前灯因按键/键盘背光默认=1.0，在亮屏时被写成 RGB=255/255/255。LineageSettings secure 的 button_brightness 和 keyboard_brightness 已持久化为 0.0；用户确认灯已熄灭。
- 音频原先用通用 WSA 后端，播放时 libar-pal.so abort。改为原机 TDM-LPAIF-RX-SECONDARY 资源配置，并合并原机 static/dynamic mixer overlays 后，audio HAL 能运行。六组 TLH/TLL/TRL/BLH/BLL/BRL AMP=On，Protection DSP，原机 TDM 四通道及 slot=2/2/0/3/3/1。六个扬声器不能误等同于六个 PCM 通道。用户确认铃声六个都响且很响，但音乐及媒体音量提示音仍只有左侧微弱声音。媒体路由仍待修复。
- Dolby 暂停试验导致音乐无声，已恢复启用；audio.offload.disable=1 和 audio.deep_buffer.media=false 只用于临时 PCM 定位，未固化为修复。
- 相机 provider r2 已原生启动，但卡在 CHXPSClient::RegisterRoutine，原因是原机 ssgtzd socket 需要 vendor_ssgtzd 用户组，首版 RC 省略了该组。短暂调整 socket 组进行诊断后 provider 立即注册，系统枚举 9 个逻辑设备、4 个公开设备；socket 已恢复原 system:vendor_ssgtzd / 0660。源 RC 已补回 vendor_thermal/vendor_ssgtzd，正在打包固化，仍需重启验证。不拍照。
- 双击亮屏及左侧电源键动画尚未修复；Xiaomi shim 的 gesture_double_tap sysfs 在实际 stock 模块不存在，需接入真实 ioctl/gesture 机制。

构建清单：reports/system-bringup-r2.json；镜像 artifacts/system-bringup-sheng-r2/。当前实机证据 reports/device/system-bringup-r2-20261106-170655/；前序临时诊断 reports/device/system-touch-20261106/。

## 以下为过时的历史记录，不能作为当前操作指令

设备 `ca10ede3`，当前槽位 `b`。用户授权自主调试、针对性刷写与重启；触摸暂缓，采用 ADB 模拟输入。未格式化或删除 userdata，SELinux 保持 Enforcing。

## 已验证的进展

- Recovery r13 的显示、misc、触摸坐标和启动延迟已经由用户验证。
- init_boot 调试 r1 已安装，系统 ADB 可用，官方 adbroot 设置已启用；实测 root 和 SELinux Enforcing。
- system_ext 权限修复 r1 已刷入 `system_ext_b`、`vbmeta_system_b`。Dolby 缺失特权权限白名单导致的 system_server 崩溃消失，实测 `sys.boot_completed=1`。
- 系统源码内核实测版本为 `5.15.220-gf9ca2b71f672`。
- 显示驱动最大时钟 514 MHz；原默认 144 Hz 的 SDM QoS 需求为 546.03 MHz，准备阶段失败。
- 将系统临时设为 60 Hz 后，定位到第二个故障：空闲 CWB 将 Virtual-1 / encoder 32 和 DSI-1 / encoder 64 同时挂到 crtc 176，内核 `failed valid clone check for mask 0x5`，返回 EINVAL。
- 临时 `vendor.display.disable_cwb_idle_fallback=1` 后，系统显示提交错误消失，设置页可通过 ADB 模拟点击操作，休眠唤醒恢复正常。不需要 `enable_force_split`，测试时已恢复 0。
- 曾通过电脑相机短暂看到完整 Lineage 欢迎页；相机随后关闭。这个结果来自临时运行状态，不能替代新镜像的重启验证。

## 当前阻塞与待修复

显示修复 ODM r1 已刷入 `odm_b`，只修改了 `etc/build.prop` 和 `overlay/FrameworkResOverlaySheng.apk`：关闭空闲 CWB，并把默认和默认峰值刷新率设为 60 Hz。实际分区大小保持 1141067776 字节，APK 资源只改变两个整数，回读内容及文件属主验证通过。

首次生成并刷入的顶层 vbmeta 漏掉了 `vbmeta_system` 链描述。`avbtool --include_descriptors_from_image` 不复制链描述，原打包检查遗漏了这一点。重启后实机停在红色 AVB 错误页（电脑相机已拍到 “Your device is corrupt” 和 “PRESS POWER KEY TO CONTINUE”）。此页没有暴露 ADB 或 Fastboot USB 端口，当前软件不能模拟这个实体电源键。

已修正打包脚本，改为保留原始完整描述符序列，只替换 ODM hashtree。修正镜像完整保留 `vbmeta_system` 的链密钥、回滚位置、顶层签名算法及原 flags=3；签名和每条原始描述符的对比均通过。原 flags=3 来自已安装 OTA，本轮没有新增降低校验的设置。

- 修正镜像：`artifacts/system-display-fix-sheng-lineage-24.0-r1/vbmeta-chain-fixed.img`，并同步覆盖该目录的 `vbmeta.img`，避免再次使用缺链版本。
- SHA256：`f0a9d448f68ee32a09e3597750089e4c8334f23b4cc42a977ee72768fdd76ed5`。
- 正确镜像尚未写入实机，重启验证尚未通过。
- 后台 `scripts/resume_display_repair.ps1` 已启动。等待最多 12 小时，等待期间不打开摄像头或麦克风；仅识别 `ca10ede3` / `sheng` / b 槽后补刷 `vbmeta_b` 并重启。如该设备的 ADB 先返回，会验证机型和槽位后进入 Bootloader。确认 boot_completed 后保存显示和音频日志，运行只读声卡控件诊断，并通过有硬超时的程序只取一帧电脑相机图后释放。
- 后台日志：`reports/device/system-boot-fix-r1-20261106-073514/resume-display-repair.txt`。PID 存于同目录 `.pid` 文件。

## 后续验证

1. 修正 vbmeta 实际补刷，确认 USB、ADB、boot_completed，验证镜像默认 60 Hz 和 CWB 属性生效。
2. 短暂打开电脑摄像头取得一帧实体屏图，立即释放。`scripts/capture_host_camera.py` 已实测能在约 3.5 秒内取图并关闭；子进程有 12 秒硬超时。Windows 相机应用曾卡启动页，不能把该 splash 当作平板画面。
3. 验证设置页、ADB 输入、息屏唤醒；然后修音频、测试 Wi-Fi、蓝牙与摄像头。触摸按用户要求暂缓。
4. 音频 HAL 当前播放时在 `libar-pal.so SessionAlsaUtils::open` abort。日志显示 AGM mixer 缺 `CODEC_DMA-LPAIF_WSA-RX-0 rate ch fmt` 和 `metadata` 控件；需要回读实际 AGM 后端列表和虚拟声卡控件，再确定配置或 ABI 原因。原厂和源码 `aif_info` 布局均为 name[32] + direction、步长 36，尚未发现该结构 ABI 差异。只读 tinymix ARM64 诊断工具已独立编译，位于 `artifacts/audio-diagnostics-sheng/tinymix`，尚待实机运行。另有 Dolbycodec2 空指针崩溃。

## 临时设置与范围

刷入 ODM 前已删除临时 `peak_refresh_rate` / `min_refresh_rate` 限制，并清除用户首选显示模式，让重启验证使用镜像默认值。`user_setup_complete` 和 `device_provisioned` 已恢复 0，保留用户自己的初始设置流程。

为了 ADB 功能测试，曾将 screen_off_timeout 设为 600000、关闭 screensaver_enabled、启用 development_settings_enabled 和 USB 保持唤醒；后续应结束测试并恢复适合日常使用的设置。临时 SDM 详细日志和 drm.debug 已关闭；不兼容的 GPU 强制合成和 libsdmextension 遮盖测试均已撤回。

未重复 sideload 整包，未启动整包重编或清理缓存。只重编了资源 overlay 并打包单一逻辑分区；资源编译复用原生成规则，保留原 SDK 和签名密钥，并对所有 APK 资源确认只有两个目标整数变化。

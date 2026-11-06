# sheng 压缩卸载状态（2026-11-06）

当前范围：无 Dolby 的默认六扬声器与压缩卸载。未拍照、未打开摄像头、未清 userdata；未启用子代理。

## 已验证的回退基线

`artifacts/system-audio-pcm-sheng-r2/` 已刷入并重启验证，用户确认六个扬声器正常。内置扬声器默认 PCM，ODM 保持原字节。该目录和 PCM 构建脚本保留。

## 卸载修复及证据

- 原先仅 PCM 应用的合法 2→4 CHMIXER 矩阵扩展到压缩流的解码后输出。FL/FR/LB/RB 输出 ID 唯一；输出行、输入列，slots 0/1 接 L，2/3 接 R；Q14 unity，不修改功放增益与保护配置。
- Stereo 压缩流先重置 stream volume master 到 Q13 unity，再按 AudioFlinger 的原左右音量配置每声道增益。用户确认熟悉的 stereo MP3 六扬声器出声，以及音量 0→12→25 的静音和音量变化正常。原 master 衰减值未成功读出，不能写为已取得芯片原值。
- 初次 AAC 与 mono MP3 独立测试用户均确认没有声音，记为失败。mono 日志有 DSP config failure 17 / Linux -61，流未启动且数据写入失败。
- CHMIXER 系数表需 4 字节内部对齐，且 APM param_size 必须包含该 padding；旧 mono 表的 param_size 少两字节。根据 AudioReach 实现修复后 -61 消失、数据写入和 DSP render timestamp 正常，但用户仍确认只在左侧出声。
- Mono MP3 保留 codec.ch_in=1，请求 codec.ch_out=2；仅在 sheng/TDM speaker 下生效。MFC 的本地属性副本匹配实际解码双声道，原流属性保持 mono，继续用原媒体 master 音量。用户随后确认 mono MP3 左右都有声音。
- AAC stereo 复测时确认真实 compressed_offload、48 kHz / AAC LC、左右增益和 PortVol 都为 0 dB、持续写入和 render timestamp 正常；用户确认左右都有声音，播放到约 89837/90000 ms 后正常停止。前次 AAC 播放时 HAL 左右增益为 0.037584；因此没有改写原 AAC codec object type 的默认行为。
- 生产属性名为 vendor.audio.sheng.offload_quad_coeff=true 和 vendor.audio.sheng.offload_master_unity=true；去掉 master 属性的 `_test` 后独立编译候选库。候选 PAL SHA256：c20ed5ddeb7b87d22e8a317f4ab5cae5bb41dc34b1f7ade84dfb0756752bf3de。

## 镜像候选

`artifacts/system-audio-offload-sheng-r1/` 已针对 vendor_b/vbmeta_b 刷写并通过重启验证。

- 相对 PCM r2 仅改 vendor 的 build.prop、sku_kalama 音频策略和 lib64/libar-pal.so。Speaker route 恢复 compressed_offload，PCM route 保留；不依赖 audio.offload.disable。
- vendor：303517696 字节，SHA256 1fb562d742ac2921a95c0ad54d8761e3a4ece1334cdbfcdc54c25170e0941d3f。
- vbmeta：8192 字节，SHA256 aac43d3bb4a7b1a2db34ac7f29b0bd2feba5407401e54bcd4e50222ba2dcf1fa。
- EROFS 全量内容/属主/权限回读、原分区大小、AVB 签名、其余完整 descriptor 及 vbmeta_system 链保留检查通过。ODM 不改，SHA256 380aac5b18d5573a8389847553ffcdfdbbf8422413548daddd3389f5bcc76b6d。
- 合并源码 patch：patches/sheng-speaker-offload.patch。单独打包脚本：scripts/package_sheng_offload_audio.py。

生产候选已完成 mono MP3 两遍播放，每遍约 10 秒时暂停 2 秒再恢复，均收到正常 completion 回调（44838/44839 ms，时长 45035 ms）。用户报告中间正好停顿两次、每次约一秒；未报告额外中断。日志：offload-release-mono-repeat.txt。

生产候选随后恢复 Twelve 的原 DJ MP3；AudioFlinger 确认 UID 10075、44100 Hz / stereo MP3、真实 compressed_offload、左右同增益。用户确认“六个都响，音量正常”。日志：offload-release-twelve-stereo-active-flinger.txt。

## 重启后的最终验证

- 证据：reports/device/system-bringup-r2-20261106-193529/。boot_completed=1、ADB root、SELinux Enforcing；候选 PAL 和策略哈希一致，三个 sheng 音频属性为 true，旧 `_test` 属性及 audio.offload.disable 为空，无音频临时 bind mount。
- vendor_b、odm_b 实体分区以及 vbmeta_b 的前 8192 字节哈希均与镜像清单一致。ODM 原字节保留。刷写输出的 sparse header 提示后两段 vendor 均明确 Sending/Writing OKAY，不能将该提示误记为刷写失败。
- 独立 stereo MP3 隔离样本实测 compressed_offload、44100 Hz / 两声道、四通道混音和单位 master 配置成功，写入和 render timestamp 正常。用户确认“低音只在左，高音只在右”；样本正常完成（71953/71962 ms，时长 72046 ms），不是 PCM 测试结果。
- 已恢复 Twelve 的原 DJ 音乐及测试前媒体音量 15；实际流为 stereo MP3 compressed_offload。用户明确确认“六个都正常，音量正常”。杜比 prefs enabled=false。
- 清单 hardware_boot_tested 和 six_speaker_playback_after_reboot 均已置 true，记录左右隔离和重播/暂停验证。

本次完成基本 PCM/压缩卸载六扬声器及左右声道修复。已测试 stereo MP3、mono MP3 和 stereo AAC；其他 codec/profile、长期连续播放和 Dolby 调校未全面验证。

所有实机测试日志：reports/device/system-bringup-r2-followup-20261106/offload-*。

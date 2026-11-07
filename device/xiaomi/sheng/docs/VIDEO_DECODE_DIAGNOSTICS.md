# 无相机、无显示的视频流诊断

r25 的组件创建/释放检查不等于实际视频帧已经通过。本探针补充完整的
MediaExtractor → 指定 MediaCodec → 内存输出路径，不使用 Surface、摄像头、
截图或解码帧文件，不接触用户媒体。输入为单独下载、固定版本和 SHA256 的
Chromium 测试片段，原始来源由上游 README 说明为 Dolby 的演示流。

## 构建与输入

ShengVideoDecodeProbe.java 已经当前平台公开 SDK、JDK21 和 D8 编译通过；
build_sheng_video_decode_probe.py 只构建，不连接设备。输出目录必须不存在。
封存的 JAR SHA256：
8888ddb90edafcd3a6adb975804cb1e8961ae9892675ca220e1f690b71c5f506。
源码、SDK、D8 哈希与实际命令在 workspace
reports/device/video-decode-probe-20261108/build-result.json。

上游固定提交 f970ac1ce7f1ccd618b000a006aa1bc80714eff9，目录：
https://chromium.googlesource.com/chromium/src/media/+/f970ac1ce7f1ccd618b000a006aa1bc80714eff9/test/data/

| 文件 | 字节 | SHA256 |
| --- | ---: | --- |
| glass-blowing2-dolby-vision-profile-5-frag.mp4 | 4537752 | d21fc3938a813b6ce25efe890074b23d966a5828c9a3d33de7e8591a25dd2036 |
| glass-blowing2-dolby-vision-profile-8-1-frag.mp4 | 3528195 | 2cbedc36cf1ec2fdaaa54d26942ff93faeda4d4b2baf9fd25ee74bfebc15287e |

两文件均经 ffprobe 容器检查为 1920x1080 HEVC，分别带 Dolby Vision
profile 5 和 8 配置；来源 URL、下载 SHA 和容器解析结果保存在 workspace
reports/device/video-decode-fixtures-20261108。容器可解析不等于实机能解码。

## 实机条件和检查

verify_sheng_video_decode.ps1 默认只核本地 JAR、源码和两个固定片段哈希；
显式 -Run 才部署和执行。脚本固定 ca10ede3、sheng、b 槽、启动完成，
逐个核对已安装 r25 七库和未改 libui/libgui 的哈希，拒绝在旧 ABI 上尝试。
它不执行 adb root。应先完成 r24 运行回归、r25 刷入及 r25 专用自动回归。

每个片段对明确指定的 c2.dolby.decoder.hevc 解码两轮。探针要求输入 track
确实声明 video/dolby-vision、能力匹配、不加密、样本完整，最多送入 60 帧后
发送 EOS。每轮必须在 45 秒内输出至少 8 帧、输出数等于输入数，并收到 EOS；
第二轮输出时间戳序列必须相同。内存输出只取样计算摘要，不保存图像。
stop 失败时仍执行 release；外层 timeout 限定应用进程运行时间。

检查 SystemUI、相机 provider、两 Dolby 服务的 PID 稳定，并保存 crash buffer。
临时路径预先要求不存在，结束或失败后清理。默认本地校验与 PS 语法检查已通过，
**尚未实机运行，不能记为实际视频流修复已通过。**

这两段清流不覆盖 DRM、安全解码、视频编码、完整时长播放、HDR 色彩准确性、
音画同步或第三方播放器的实际路径；这些继续分别保留未验证状态。

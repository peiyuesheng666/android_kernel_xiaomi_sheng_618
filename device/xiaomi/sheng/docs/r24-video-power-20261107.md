# r24 Dolby 视频生命周期与电源键位置批次（构建审查通过）

11-08 01:04 左右已向 b 槽写入 r24 四个镜像并发出重启，尚未恢复目标 ADB，
启动和运行验收未完成。r23 AON、显示、普通触摸、常用视频和
扬声器声音已获用户确认；保持型号 24018RPACC、营销名、平板兼容和设置页面。

## 视频组件释放

原厂 c2.dolby.hevc.dec.so 中 0x11c7c 构造的 AHandler 子类把成员放在
偏移 96/104。当前平台 AHandler 在 +96 放 mLock，deliverMessage 的
状态记录访问覆盖这个旧成员区。r23 真实现场卡在该状态锁，继而使
SimpleC2Component::release 和客户端死亡清理等待消息回复。

独立原生探针不能只 createComponent/release：还必须 setListener_vb，
让 WorkHandler 持有弱 self，release 才实际执行原厂 onRelease。最初
没有该步骤的成功结果不构成复现或修复证据，原始输出全部保留。

2026-11-07 独立诊断进程结果（不替换系统服务，不配置或输入视频流）：

- 基线补齐监听器后释放超时，timeout 退出 124。
- 第一候选改四个库，解码/编码各十次创建、监听器绑定和释放通过。
- 收窄为第二候选，只改普通/安全解码两个库的 foundation 符号导入及
  DT_NEEDED，使用已验收私有 libshgdolby_foundation.so。
- 最小候选普通解码十次通过，5 秒 CPU 增量 0；安全解码三次通过，
  5 秒 CPU 增量 1 tick（100 ticks/s）。没有建立 DRM 会话或验证受保护播放。
- 11-08 补测最小候选下的原厂编码库，十次创建、监听器绑定和释放通过，
  5 秒 CPU 增量 0，退出 0；没有配置媒体或替换系统服务。
- 编码库、处理器库、SimpleC2Component 和共享平台 foundation 不作修改。

证据位于 workspace reports/device/r24-investigation，特别是
baseline-decoder-listener.txt 与 candidate2-*-listener.txt。
系统服务与媒体播放仍待正式构建、刷入后验证。

## 电源键动画

上游 PowerButtonReveal 的默认原点位于右边，且没有自然方向 180 度分支；
WakefulnessLifecycle 只按横竖屏映射。sheng 是自然横屏、左边缘电源键。
设备专用纯几何实现将左边缘原点按四个实际 display rotation 旋转，保留
上游插值、透明度、椭圆半径和 5% 屏外起点。电源键原始 Y 资源仍使用
系统值，不伪造精确测量值；原厂 MiuiSystemUI 同名默认资源也是 620px。

实现全部位于设备树：对上游产出的 APK 精确替换两个方法，添加两个
设备 helper 类，资源与 manifest 字节保持，再走标准 platform 签名。
任何目标方法签名变化或数量不符均构建失败，不修改公共源码。
历史未跟踪 interfaces/systemui 候选保持原样，不纳入安装。

11-08 正式构建通过，仍不能据几何测试或 APK 变换成功列为实机已修复。

独立审查发现 R8 已移除没有读取用途的 interpolatedRevealAmount setter 和
R 类。helper 去掉无效 setter 调用，按名称解析原有资源，避免运行时链接失败。
固定上游 dexlib2 重写原厂优化调试程序时会生成少量无效参数调试表；设备
patcher 仅在重新编码的 DEX 中去掉可选调试名字/行号，保持代码、异常处理、
注解与签名。未重写的 DEX 保持原字节。对已有 37424 个类的独立语义审查通过，
只有两个方法体改变、两个 helper 加入，所有资源及清单字节保持；输出全部
debug programs 再遍历无异常。11-08 正式 Soong 签名产物再次通过全部审查，
平台证书与原 APK 一致；六种缺目标、重复类、DEX 索引断档、改名、错误 helper、
重复变换输入均被拒绝。几何 66 项断言通过。

封装 helper 的目标路径/真实构建来源映射及 ext4 集成共 15 项测试通过。
APK 输出独立语义审查与六类异常输入测试均已通过。
完整产品也保留原 SystemUI 所需的 wmshell.protolog.pb；本批镜像仅替换
既有 SystemUI APK，既有其他文件与节点元数据仍须保持。

## 用户触发的相机崩溃（下一批线索）

2026-11-08 用户反馈启动后仅出现零点几秒预览便报错退出。读取已有日志，
未启动相机、AON 或重启 provider。设备日志使用 UTC，11-07 16:06 对应
本地 11-08 00:06。两个 tombstone 的原生首发崩溃均是 camera provider 在
GraphicBuffer 析构时访问已损坏的 DependencyMonitor 字段；Aperture 随后
因 camera id 0 不再可用退出，故不能仅修应用异常处理来认定相机已好。

原厂 camera.xiaomi.so 的四个 GraBuffer 构造路径仍为 GraphicBuffer 分配
256 字节。用当前 vendor libui 的实际编译参数检查头文件记录布局，大小
为 3376 字节，原 256 字节之后增加 DependencyMonitor。这是明确的分配
ABI 不匹配；需完整核对各分配点，再在独立、受限诊断中验证，不在运行中
覆盖相机库或启动摄像头。原始日志、反汇编、编译参数和布局保存在
reports/device/r24-investigation/camera-*。

导入清单还发现原厂 Dolby 视频三库、grallocutils、mawutils、vidhance 和
libgui_vendor 使用 GraphicBuffer 构造器；不据此假定它们所有路径都已验证。
r24 的视频验收首先针对已复现的 AHandler 释放与创建生命周期；流配置和
真实视频缓冲分配另行检查，不能由分配/释放通过推断完整 Dolby 视频播放。

11-08 独立 libui 内存探针分别执行空构造和空 handle 包装各 100 次，未加载
相机 HAL、未采集图像。构造函数确实改写旧 256 字节之外的 936 字节；
按当前 3376 字节分配后，构造、非释放析构两阶段前后红区均保持完整。
八个原厂库共 31 个直接构造调用点已列入核对。进一步核对当前安装来源，
libgui_vendor 已从当前公共源码编译，并非原厂副本；实际候选范围收窄到
七个原厂库的 14 个分配点，修正尚未安装。

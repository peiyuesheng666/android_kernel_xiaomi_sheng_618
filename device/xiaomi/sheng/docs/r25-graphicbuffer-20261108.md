# r25 相机与视频 GraphicBuffer 分配兼容（构建审查通过）

r24 的四个镜像已写入 ca10ede3 的 b 槽并重启；目标连接尚未恢复，
因此 r24 启动、动画及视频服务回归仍未验收。本批未刷入。
另一台官方澎湃平板没有进行任何操作。

## 相机

用户触发的相机 provider 崩溃在 GraphicBuffer 析构的 DependencyMonitor
字段。原厂 camera.xiaomi.so 的四个 GraBuffer 构造路径分配 256 字节；
当前 vendor 头文件和实机 libui 对应 3376 字节。grallocutils、mawutils、
vidhance 的七个同类分配也保留旧大小。

设备树新增非安装 C++ 布局归档，使用当前 vendor libui 头文件编译并记录
真实 sizeof。七个生成库依赖该归档，仅对经过核对的 256/3376 字节布局
放行，并检查 RefBase、ANativeWindowBuffer 的大小、对齐及公开字段前缀。
布局、输入哈希或原指令不符便失败，不修改公共头文件或共享 libui。

第一项设备提交 175218a：相机及三处处理库，共 11 个精确分配指令。
不加载相机 HAL、不开启摄像头、不重启 provider。相机预览尚待用户验收，
不能用候选生成或空对象测试替代。

## Dolby 视频缓冲

第二项设备提交 b137b84：普通解码、安全解码和编码三个库各一处分配。
两个解码输入保持 r24 的独立 AHandler 符号路由，编码库的 foundation
依赖保持原样。此处处理的是实际视频缓冲对象内存越界风险，与 r24
已复现的释放消息锁问题分别记录；实际媒体流和受保护内容仍未验证。

最初对原厂八个库核对了 31 个构造调用。当前安装 libgui_vendor 是
平台源码重编版本，哈希 0b082826f4787ea3332e282e7c9de877c4e7384d388bdb68fdb7fbcdf0b231c3，
已经使用新头文件，不纳入本批。最终范围为七个原厂库、14 处分配。

## 自动检查与边界

- 采用真实 vendor 编译参数的独立 libui 探针在 r23 执行空构造和空 handle
  包装各 100 次。构造写入旧 256 字节之外的 936 字节；按 3376 字节分配，
  构造/析构两阶段前后红区完整，探针已清理，未采集图像。
- 预先候选七个库全部通过独立字节和反汇编审查，14 处变为 3376；构造调用
  地址和其余字节保持。未知大小、错误对齐、截断归档、缺符号及错误原库
  五种异常输入被拒绝。正式 Soong 安装产物已重复通过相同审查，和预先候选
  逐字节相同；七个原有安装模块的 ELF 检查均通过。
- 增补的离屏 gralloc 客户端探针已编译，计划对真实修正库运行 100 次
  分配与释放；尚未执行，不列为通过。它不调用相机 HAL。
- 封装 helper 的 15 项检查通过，新增基线文件哈希记录及断言。
- 封装仅替换 ODM 四库、vendor 三库，并更新 vbmeta 中这两个子描述符；
  核对原库哈希、未改的 libui/libgui、AON 目标和链接，保留所有节点元数据。
  r24 SystemUI 和 vbmeta_system 保持；正式构建首次通过，镜像待封装。
- 刷机脚本先核验六个实机 r24 基线；验证脚本不执行 adb root，不调用
  attention，不开相机，不擦数据或切槽。人工观感与预览明确留空。

证据：workspace reports/device/r24-investigation/camera-*、
graphicbuffer-abi-probe-r25.txt、graphicbuffer-reviewed-allocation-sites.json，
以及 reports/device/r25-investigation。未将任何离线成功列为实机相机已修复。

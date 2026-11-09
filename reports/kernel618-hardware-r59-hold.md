# r59 启动等待实测（2026-11-10）

按用户要求重新启用驱动加载前 8000 毫秒等待。复用 r57 已编译的
`pre_driver_hold_ms` 实现，gzip 封装为 r59；内核和内嵌模块逐字节保持 r57。
当前 r58 内核没有该实现，因此未向 r58 直接追加无效参数。

`sheng_bootlog_init` 的 late_initcall 在 Android init 加载板级模块之前调用
`msleep`，起止写入内核日志；参数默认零，正常版本不会额外等待。
这次是既有诊断代码的重新启用，不是白闪修复。封包脚本新增参数、检查内核
确实含等待实现，兼容已有 gzip 输入，并回读验证完整命令行。

- boot SHA256：`087c45d23264bdfc7a9f2247bccba37af206285c349acb50eeb0da6757b91993`
- Image SHA256：`4d921a09561486488443c5c3a423e4f3d1a0357b293f326747a94ac7326230ab`
- logger 源码 SHA256：`35acd863f6ccd91516f6134c8fbd465f6ad9b49f38f41685a9195d91be864b91`；工作区与 WSL 逐字节一致。
- gzip 解压、内核字节、空 ramdisk、命令行回读、AVB 校验与 Python 语法检查通过。
- 06:00:56 +08 完成刷写 boot_a 并重启；刷前核对 sheng、a 槽、unlocked=yes、is-userspace=no。
- 首次实机等待开始 0.400183 秒、结束 8.419157 秒，间隔 8.018974 秒；启动完成、USB online=1。
- 后续启动回读 revision=hardware-r59、pre_driver_hold_ms=8000、test_timeout=0、boot_completed=1、USB CONFIGURED。
- 后续完整日志等待开始 0.402032 秒、结束 8.419194 秒，间隔 8.017162 秒。
- 用户反馈：Logo 先停留约 8 秒，之后才白闪。故障范围缩小到等待之后，尚不能据此确定具体驱动。

后续完整原始日志保存在本地 `reports/device/kernel618-hardware-r59/kernel.txt`，
SHA256 为 `e060947ca39f360baecc345aedf2d8376f9e019623459e768a1339f522a58f4f`。
其中 DISP CC 首次 runtime resume 在 8.883032 秒，已晚于等待结束。
仅刷 boot_a；原厂包保持只读，不擦分区、不备份当前 boot，不启用定时重启。
交付目录保留 r55–r59 共五版。白闪、笔轻写断续/重复点击继续排查。

# Sheng ADB 5555

用户于 2026-11-09 明确授权制作此模块，用现有 root 在每次开机后开启
无线 ADB TCP 5555，供内核连续调试。使用现有 KernelSU/SukiSU、Magisk 或
APatch 的模块接口安装；本模块不提供 root，不往内核加入 GKI root。

`service.sh` 启动一个后台进程，每 15 秒检查 ADB 的运行端口和 adbd 状态，
只在配置改变或服务未运行时请求重新启动 adbd。系统启动完成后确保
`adb_enabled=1`，设置提供者就绪前也会先尝试启动监听。保留 ADB 身份认证
和已有电脑的授权，不修改 `ro.adb.secure`、ADB 密钥或 SELinux 模式。

模块使用 `service.adb.tcp.port` 与 `service.adb.listen_addrs`，不写持久的
`persist.adb.*` 属性。保存安装前的 ADB 设置，停用或卸载时恢复。日志只
记录服务与配置操作，单个日志约 64 KiB 后轮换，保留当前和上一份。
查看 `/data/adb/modules/sheng_adb_5555/service.log` 可核查操作是否成功。

电脑通过 `adb connect <平板当前 IP>:5555` 连接。仍需平板连接 Wi-Fi，且
必须由现有 root 框架成功执行模块；源码与安装包校验不能代替重启实测。

接口依据：本地固定 Android ADB 源码的 `daemon/main.cpp` 优先读取
`service.adb.listen_addrs`，否则读取 `service.adb.tcp.port`；模块只通过这些
已有接口启用监听，不修改 ADB 二进制。

# 小米平板 6S Pro WALT 内核 · 20261114

补回完整 Qualcomm WALT 负载统计和 walt 调速器，解决原厂 post-boot 找不到 WALT 而保持 performance 的兼容差异。三个 CPU 策略已由原厂脚本自动选择 walt，实机自动降频与 8 个 CPU 的 C4 深度空闲均通过验证。

保留手写笔 v4、必要的原厂温控／充电消息接口与 qcom_lpm 空闲修复。未恢复已取消的 Oplus 扩展及存储、内存、整机工厂调试接口；本轮没有提高温控阈值或伪造温度。

WALT 源码来自 CodeLinaro kernel.lnx.6.12.r70-rel，固定提交 46f13428ae2d6e32ddfe2f3e5cb5046428ae73b4，共 24 个构建对象。内核分配真实任务 vendor tail，新增 arch_task_struct_size 和 fair_sched_class 导出。保留原有 18,038 个导出 CRC。boot 增加 sched_proxy_exec=0，使用原厂 WALT 支持的经典调度模式。

已通过 103,612 个源码文件哈希、41 个 WALT 源码补丁回放、345 模块 ABI/BTF、boot 解包和 AVB 校验。镜像已经刷入 HyperOS OS4.0.2.0.XPYCNXM 的 sheng 平板并完成重启验证。

2026-11-14 07:40–07:50，同一个酷泰科充电宝熄屏复测约十分钟。起始电量 30%、电池约 27°C，结束电量 57%、电池约 32°C。输入功率估算从约 74W 平缓下降到约 57–59W，用户看到最低仍约 60W。温控档位保持 0，限流原因按 StepChgJeit 档位变化，没有再次出现 thermal-9000，也没有重现上一版骤降到约 40W 的故障。日志归档下载前后 SHA256 与 61 个解包文件回读通过。

本次验收覆盖上述设备、系统、充电宝和约十分钟的条件。原有 /data 温控覆盖独立于 boot 和源码包；当前构建没有打包或改动该覆盖。

Image 为内核镜像，boot.img 为原厂模板打包后的启动镜像。完整源码包包含固定源码输入；Git 克隆或项目 ZIP 使用同一 Release 的 sheng-kernel-build-inputs.tar.gz。工具链和匹配的原厂 boot 模板按 [构建说明](BUILD.zh-CN.md) 准备。

实际改动与镜像校验值见 [来源记录](../provenance/walt-charge-release.json)。根目录四阶段入口按来源哈希回放补丁，使用隔离的原生 Linux 编译目录。构建入口不刷设备。

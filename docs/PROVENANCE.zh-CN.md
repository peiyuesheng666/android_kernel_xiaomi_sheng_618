# 来源与源码回放

当前构建以 `provenance/release.json` 和功能文档为准。
`source-plan.json` 等历史来源记录保留早期规划事实，旧路径和版本号不作为当前下载入口。

ACK来自固定 `ff4a6c3bb0f471a9dd186293a47b62c83829b97d`（6.18.32）。参考项目为
JiaqiLi404/android_kernel_618_for_sm8550，固定
`c3956156ce7c4193c451dfda531fad72d35bfebb`。MiCode、LineageOS、Droidspaces来源
及固定提交记录在provenance；原SPDX和许可文件保持。

`assets/sheng-kernel-build-inputs.tar.gz` 是已适配基线，不是纯上游源码。
prepare-inputs.py验证缓存哈希、执行记录的路径修正、核对基线逐文件哈希，
再按序确认双电池认证、SYSVIPC、SoC、手写笔/release和最终充电补丁。
已应用补丁由哈希识别，不重复修改；未知内容与部分应用会拒绝构建。
最终源码103610个文件；生成camera编译身份头只允许规定的三行元数据。

`provenance/repair-r85.json` 沿用旧文件名，实际revision为repair-r87。
`patches/sheng-repair-r87.patch` 是r76到r87的组合补丁。
r85/r86补丁保留为审计阶段；构建只回放最终r87组合补丁。
`kernel/charging/` 提供七个充电源码的精确审核副本，构建使用外部
BUILD_ROOT中的对应文件。修改审核副本本身不会更改构建输入。

这是固定缓存加补丁的可复现工程；未实现从每个干净上游仓库重新重演全部移植。
427条原共享开发历史保存在独立port-history分支及离线bundle，见HISTORY.md。


## 当前依赖包命名

固定源码输入以 `sheng-kernel-build-inputs.tar.gz` 交付。
此次只更新交付文件名与引用，压缩包字节和 SHA256 保持不变。
`source-cache.json` 的 `prefix` 与基线 `revision` 保留归档内部的原始名称，
用于严格解包与来源追溯；它们不表示仍提供或需要安装旧内核。
当前构建仍按原有补丁链生成当前内核源码，现有 Image/boot 内容保持不变。

当前版本的 WALT、手写笔 v4、温控／空闲叠加补丁和硬件验证范围见 [发布说明](WALT-CHARGE-20261114.zh-CN.md) 与 [来源记录](../provenance/walt-charge-release.json)。

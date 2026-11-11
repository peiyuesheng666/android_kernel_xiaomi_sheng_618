# 来源与源码回放

当前状态以 `provenance/release-r87.json`、r87功能文档和r87验证记录为准。
`source-plan.json`、`hardware-acceptance.json`、r71记录等保留早期规划/采样事实，
其中旧目录、初始状态和交付方式不描述当前版本。

ACK来自固定 `ff4a6c3bb0f471a9dd186293a47b62c83829b97d`（6.18.32）。参考项目为
JiaqiLi404/android_kernel_618_for_sm8550，固定
`c3956156ce7c4193c451dfda531fad72d35bfebb`。MiCode、LineageOS、Droidspaces来源
及固定提交记录在provenance；原SPDX和许可文件保持。

`assets/sheng-6.18.32-release-r71-source.tar.gz` 是已适配基线，不是纯上游源码。
prepare-inputs.py验证缓存哈希、执行记录的路径修正、核对基线逐文件哈希，
再按序确认双电池认证、SYSVIPC、SoC、手写笔/release和r87充电补丁。
已应用补丁由哈希识别，不重复修改；未知内容与部分应用会拒绝构建。
最终源码103610个文件；生成camera编译身份头只允许规定的三行元数据。

`provenance/repair-r85.json` 沿用旧文件名，实际revision为repair-r87。
`patches/sheng-repair-r87.patch` 是r76到r87的组合补丁。
r85/r86补丁保留为审计阶段；构建只回放最终r87组合补丁。
`kernel-6.18/charging/` 提供七个r87充电源码的精确审核副本，构建使用外部
BUILD_ROOT中的对应文件。修改审核副本本身不会更改构建输入。

这是固定缓存加补丁的可复现工程；未实现从每个干净上游仓库重新重演全部移植。
427条原共享开发历史保存在独立port-history分支及离线bundle，见HISTORY.md。

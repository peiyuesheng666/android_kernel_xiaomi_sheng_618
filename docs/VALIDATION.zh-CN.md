# r87 验证

```bash
bash scripts/run-limited.sh verify
bash scripts/test-charging.sh
```

verify核对源码哈希、补丁receipt、模块路径、符号链接边界、脚本语法。
存在完整构建时核对Image/boot、内嵌配置、344模块ABI以及最终split BTF。
当前保留构建全量验证通过：103610源码文件、344模块、21021版本导入、ABI问题0，
所有模块BTF通过。详见provenance/r87-post-cleanup-validation.json。
这份报告验证已有构建；GitHub整理没有重新完整编译，不能当成新的独立编译结果。

test-charging.sh从准备后的生产源码提取回调，运行ASan/UBSan主机故障注入，
覆盖属性编号/格式、非法输入、溢出、glink断开/错误、文本截断/无NUL、
工厂轮询超时/分配失败、PPS识别/原装优先、batterysecret写0、认证/健康/暂停、
通知/禁用/连接竞态与失败预算。结果写dist/repair-r87/host-tests/。
主机shim不能替代真实固件、并发调度及实机充电验证。

已验证现有产物SHA256：

```text
479bea2cfa166228c7cb8581460569c20c3e6cb7bd6875cdf05a581f59feff3f  boot.img
fd76e0431b4f69ff375cadf37364e64f4960b278afe8eb0e248c88528dae2ec9  Image
```

发布时另外验证Git实际提交的项目从固定缓存全新回放可得到同样最终源码，
并核对新的发布源码包完整读回以及GitHub资产digest。结果见release-validation.json。
实际硬件边界见FEATURES-REPAIR-r87.zh-CN.md，编译通过不代表全部硬件正常。

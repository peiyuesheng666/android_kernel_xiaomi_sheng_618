# 本地检查入口

准备源码与工具链后可运行：

```bash
bash scripts/run-limited.sh verify
bash scripts/test-charging.sh
```

verify检查源码/补丁哈希、模块路径、符号链接和脚本语法；有完整构建时还核对
Image/boot、内嵌配置、模块ABI与split BTF。
test-charging.sh从准备后的生产源码生成主机故障注入测试。
本地生成的结果保存在dist/，不会纳入Git或Release发布文件。

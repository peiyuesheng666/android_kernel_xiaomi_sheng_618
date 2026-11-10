# 验证

```bash
bash scripts/run-limited.sh verify
```

检查适配源码哈希、标准 ACK 根目录、344 个模块的路径、符号链接边界和脚本语法。
完成完整构建后，进一步核对 Image/boot.img 的哈希以及构建记录，输出
`dist/release-r70/validation.json`。

内核与模块编译脚本遇到错误立即停止；depmod 不允许未解析符号；内嵌模块层的
重编必须保持内核导出符号和 CRC 不变。实机测试须单独记录，编译通过不代表
硬件全部正常。

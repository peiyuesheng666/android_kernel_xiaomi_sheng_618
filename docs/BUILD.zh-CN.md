# 构建

在 Linux/WSL 原生文件系统中解压项目。宿主安装 bash、make、gcc/g++、jq、
rsync、flex、bison、bc、cpio、kmod、gzip、libssl-dev、libelf-dev、libzstd-dev
和 Python 3.11+。运行资源限制入口需要 root 或已委托的 cgroup-v2 控制权；
当前 WSL 未启用 systemd，因此入口直接创建独立 cgroup，限制整个编译进程组。

默认 BUILD_ROOT 为当前账户的 `~/sheng-618-project-build`，可以显式设置到
另一个空的原生 Linux 目录。bootstrap 不会覆盖非空、未准备的目录。

## 工具链

使用 provenance/kernel-manifest.xml 固定的 Google prebuilts，要求以下布局：

```text
PREBUILTS/
  clang/host/linux-x86/clang-r584948c/
  rust-toolchain/linux-x86/1.91.1.p3/
  clang-tools/linux-x86/bin/bindgen
  kernel-build-tools/linux_musl-x86/bin/pahole
  build-tools/linux-x86/bin/
```

默认 PREBUILTS 为 `$BUILD_ROOT/k618/ws/prebuilts`。已有工具链可通过
`export PREBUILTS=/path/to/prebuilts` 使用。固定工具链仓库与版本见
`provenance/toolchains.json`；不要用宿主自带 clang 替代。

elfutils 使用 0.193 并启用 zstd，安装前缀通过 `ELFUTILS` 指定，默认是
`$BUILD_ROOT/host-tools/elfutils-0.193`。需有 include/elfutils/libdw.h 和 lib/libdw。

## 执行

```bash
bash scripts/run-limited.sh bootstrap
export PREBUILTS=/path/to/prebuilts
export ELFUTILS=/path/to/elfutils-0.193
bash build.sh --config-only
bash build.sh
bash scripts/run-limited.sh verify
```

构建顺序为 ACK Image/modules → SoC → techpacks → 平板专用驱动 → 加载器。
所有外部模块均使用 `make -C ws/common O=out-gki M=源码目录 modules` 编译，
前序模块的 Module.symvers 通过 KBUILD_EXTRA_SYMBOLS 传递。

脚本汇总 344 个模块到 `out-gki/layer/lib/modules`，生成依赖清单并打包
`overlay.cpio`，再编译内置该模块层的 Image。重编前后内核导出符号及 CRC
必须完全相同。最终文件复制到 `dist/release-r70/`。

## boot 镜像

```bash
bash build.sh --stock-boot /path/to/sheng_OS3.0.303_boot.img
```

仅接受 SHA256 为
`4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea`
的原厂 boot 模板。打包得到与其分区大小相同的 boot.img，使用 header v4、
原始版本字段（此模板未设置版本和补丁日期）、`loglevel=4` 命令行及未签名 AVB hash footer。
原厂模板只读，构建脚本不执行 adb/fastboot 或刷写分区。

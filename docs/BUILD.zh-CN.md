# 内核构建

在 Linux/WSL **原生 Linux 文件系统**中放置项目与构建目录，路径不得有空格。
准备 bash、make、gcc/g++、jq、rsync、flex、bison、bc、cpio、kmod、gzip、
libssl-dev、libelf-dev、libzstd-dev，以及 Python 3.11+。Ubuntu 22.04 使用
带 `tarfile` data filter 支持的更新 Python 3.11。默认 `PYTHON=python3.11`。
资源限制入口要求 root 或已委托的 cgroup-v2 控制权。默认 JOBS=4，上限4。

## 获取完整源码

完整源码包包含当前项目、固定源码输入和 Git 历史。

~~~bash
gh release download --repo peiyuesheng666/android_kernel_xiaomi_sheng_618 --pattern sheng-kernel-source.tar.gz
tar -xzf sheng-kernel-source.tar.gz
cd sheng-kernel
~~~

Git 克隆的项目可从完整源码包取出 assets/sheng-kernel-build-inputs.tar.gz，放入项目的 assets/。
工具链及匹配的原厂 boot 模板按下面的布局单独准备。

## 工具链与打包模板

固定 Google 工具链仓库/提交见 `provenance/toolchains.json` 和
`provenance/kernel-manifest.xml`，布局如下：

```text
PREBUILTS/
  clang/host/linux-x86/clang-r584948c/
  rust-toolchain/linux-x86/1.91.1.p3/
  clang-tools/linux-x86/bin/bindgen
  kernel-build-tools/linux_musl-x86/bin/pahole
  build-tools/linux-x86/bin/
```

不要用宿主 clang 替代固定版本。elfutils 使用0.193，启用zstd，ELFUTILS前缀
须包含 `include/elfutils/libdw.h` 与 `lib/libdw`。工具链不是源码包内的输入。

提供自己的原厂 boot 模板；mkbootimage.sh仅接受 SHA256
`4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea`。
模板不随 GitHub 上传。输出 header v4、空 ramdisk、192 MiB boot分区镜像，
保留模板版本字段并添加未签名 AVB hash footer。

## 四阶段构建

```bash
export BUILD_ROOT="$HOME/sheng-kernel-build"
export PREBUILTS=/path/to/prebuilts
export ELFUTILS=/path/to/elfutils-0.193
export STOCK_BOOT=/path/to/sheng-stock-boot.img
export SHENG_BUILD_MODE=release TAG=kernel
bash buildkernel.sh
bash buildmodules.sh
bash embed.sh
bash mkbootimage.sh
```

`BUILD_ROOT` 必须在项目外；新目录必须为空。仅检查配置可运行
`bash buildkernel.sh --config-only`；全部四阶段也可用 `bash build.sh`。
最终文件在 `dist/kernel/`。模块顺序为 ACK→SoC→techpacks→平板驱动→加载器，
使用KBUILD_EXTRA_SYMBOLS传递符号版本。345模块汇入模块层并嵌入Image。
模块使用共享符号版本和 split BTF。

默认release：rawdump关闭，无300秒自动回fastboot。debug仅显式设置时启用。
所有构建入口均不会执行adb/fastboot或写设备分区。

`port-scripts/`仅为历史过程，包含旧绝对路径与设备操作；不是构建入口。

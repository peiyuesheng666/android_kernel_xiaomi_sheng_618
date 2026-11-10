# Xiaomi Pad 6S Pro · Linux 6.18.32

[中文说明](README.zh-CN.md)

A sheng release-r70 project organized like
https://github.com/JiaqiLi404/android_kernel_618_for_sm8550 at
c3956156ce7c4193c451dfda531fad72d35bfebb.
Build recipes and provenance live here; prepared ACK and external-module sources
live in an independent native Linux BUILD_ROOT. The included source cache is the
fully adapted release snapshot. Bootstrap prepares that cache offline; it does
not replay the complete historical port from pristine upstream repositories.

```bash
bash scripts/run-limited.sh bootstrap
bash build.sh
bash scripts/run-limited.sh verify
```

See docs/BUILD.zh-CN.md for pinned toolchains, dependencies and boot packaging.
All kernel/module build stages use Bash. No build script flashes a device.

# Xiaomi Pad 6S Pro (sheng) — Linux 6.18.32 repair r87

[中文说明](README.zh-CN.md) · [Build](docs/BUILD.zh-CN.md) ·
[Features and device evidence](docs/FEATURES-REPAIR-r87.zh-CN.md) · [History](docs/HISTORY.md)

Current release: **repair-r87**, default release profile, 344 embedded modules.
Includes dual-battery authentication, container networking/IPv6 NAT, SoC identity,
pen charging interfaces, 57 restored shipping charging nodes, battery bypass,
immediate eligible third-party PPS verification and split-BTF rebuild fixes.
The existing 32 ms stylus filter is retained. Hardware limitations are documented.

This repository contains the build recipes, configurations, patches, source
review copies and pinned provenance. Full ACK/SoC/techpack sources are delivered
in the release and prepared into an external native Linux `BUILD_ROOT`.
The source cache is an adapted r71 baseline; replaying the retained patches
produces the exact r87 inputs. Historical scripts are not required for building.

Download the r87 release assets from this repository. For a Git clone, place
`sheng-6.18.32-release-r71-source.tar.gz` in `assets/` and verify its hash.
The `sheng-6.18.32-repair-r87-source-with-inputs.tar.gz` package already includes it.

```bash
export PREBUILTS=/path/to/pinned-prebuilts
export ELFUTILS=/path/to/elfutils-0.193
export STOCK_BOOT=/path/to/sheng-stock-boot.img
bash buildkernel.sh
bash buildmodules.sh
bash embed.sh
bash mkbootimage.sh
bash scripts/run-limited.sh verify
```

Build scripts do not flash a device. Release images match the verified local
r87 boot/Image hashes. This upload does not introduce a new kernel build.
Original r70 commits remain in main history; the separate `port-history` branch
retains the 427 original shared-project commits. Old release downloads are retired.

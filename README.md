# Xiaomi Pad 6S Pro Kernel

[中文说明](README.zh-CN.md) · [Build](docs/BUILD.zh-CN.md) ·
[Features](docs/FEATURES.zh-CN.md) · [Source provenance](docs/PROVENANCE.zh-CN.md) ·
[Checks](docs/VALIDATION.zh-CN.md) · [History](docs/HISTORY.md)

Download: **[Current kernel](https://github.com/peiyuesheng666/android_kernel_xiaomi_sheng_618/releases/latest)**.
This is the Linux 6.18.32 port for Xiaomi Pad 6S Pro (`sheng`, Snapdragon 8 Gen 2 / SM8550),
developed against HyperOS **OS3.0.303.0.WNXCNXM**. The default release profile embeds
**344 modules** in `Image`. Use the matching device and firmware; other devices and ROMs
need their own validation.

## Included features

| Area | Current implementation |
| --- | --- |
| Battery and charging | Dual-battery authentication; 57 restored stock charging nodes; battery bypass control separate from input suspend |
| Third-party PPS | Automatic verification after eligible PPS identification; immediate recovery after a system reset to zero; stock-charger authentication takes priority |
| Containers | SYSVIPC, IPC/PID/user namespaces, IPVLAN/MACVLAN/VXLAN, VLAN/bridge, overlay filesystem and built-in IPv6 NAT/MASQUERADE |
| Device integration | SoC ID 536 maps to KALAMAP for Scene; stock pen charging sysfs/uevents; existing 32 ms stylus filter retained |
| Release and build | Rawdump and the 300-second fastboot timer disabled by default; module relinking fixes stale split BTF |

See [the feature document](docs/FEATURES.zh-CN.md) for property details and limits.
Charging protocol ratings and 90 W / 120 W animations do not establish actual input power.
Long-term pen stability, every charger and all device hardware have not been fully validated.
The cancelled wind scheduler and the Linux 7.2 zram/swap work are absent from current.

## Download

Open **[repair-current Release](https://github.com/peiyuesheng666/android_kernel_xiaomi_sheng_618/releases/latest)**
with an account that has access to this private repository.

| Asset | Purpose |
| --- | --- |
| `boot.img` | Kernel boot image, 192 MiB, boot header v4 |
| `Image` | Kernel image containing the module layer |
| `sheng-kernel-source.tar.gz` | Complete build project with the required fixed source input included; recommended for an offline source download |
| `sheng-kernel-project.zip` | Build project without the large source input; requires the build-input asset below |
| `sheng-kernel-build-inputs.tar.gz` | Fixed adapted ACK/SoC/techpack/board source input for a Git clone or project ZIP |
| `sheng-port-history.bundle` | Offline copy of the original 427 development commits |
| `FEATURES.zh-CN.md`, `SHA256SUMS` | Feature reference and release file checksums |

The build input is a dependency of the build project. Bootstrap checks its hash,
relocates the source paths and replays the retained patches to obtain the current kernel source tree.
Full source packages already contain it. No retired release download or deleted local
project is needed. Toolchains and the stock boot template are supplied separately.

## Build

Keep both the project and its external `BUILD_ROOT` on a native Linux filesystem.
The [build guide](docs/BUILD.zh-CN.md) covers dependencies, pinned toolchains and the
required stock boot hash. After obtaining those inputs:

```bash
export BUILD_ROOT="$HOME/sheng-kernel-build"
export PREBUILTS=/path/to/pinned-prebuilts
export ELFUTILS=/path/to/elfutils-0.193
export STOCK_BOOT=/path/to/sheng-stock-boot.img
export SHENG_BUILD_MODE=release TAG=kernel
bash buildkernel.sh
bash buildmodules.sh
bash embed.sh
bash mkbootimage.sh
bash scripts/run-limited.sh verify
```

Outputs go to `dist/kernel/`; `bash build.sh` also runs all four build stages.
Build entry points do not flash a device. `port-scripts/` preserves historical process
scripts and is separate from the supported build entry points.

## Project layout and release scope

`scripts/` holds input preparation, patch replay and checks; `profiles/` and
`sheng_defconfig` define the build; `patches/` and `provenance/` pin the source changes.
`kernel/` includes board ports and charging source review copies. Full build inputs
are prepared outside Git into `BUILD_ROOT/k618/`.

This documentation/package update preserves the existing `boot.img` and `Image`.
Local test results stay in `dist/` and are not release assets. An independent
`/data/vendor/thermal/config/thermal-normal.conf` override is outside the kernel and
source packages; flashing boot alone does not remove it. Original commits remain in
history; the `port-history` branch retains the shared kernel/device-tree development history.

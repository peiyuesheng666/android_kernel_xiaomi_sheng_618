# Xiaomi Pad 6S Pro 12.4 — sheng

Standalone LineageOS 24.0 device configuration for model **24018RPACC**.
The device codename is **sheng**; its board/firmware identifier is **N81A**.

All new board fixes are maintained in this device tree. Public source must
match the manifest-pinned upstream revision before building; see
[`docs/SOURCE_POLICY.md`](docs/SOURCE_POLICY.md). On 2026-11-06, fresh upstream
fetches and physical byte/type checks passed for 176,270 files across 13
previously affected public repositories; all 1,243 repo-managed projects had
clean Git status. The exact receipt is
[`docs/upstream-source-audit.json`](docs/upstream-source-audit.json).
Device-owned replacement modules are being compiled; this source audit is
not a claim that the new images have passed hardware testing.

## Work records and commits

After completing each change, debugging task or documentation task, update the
workspace README or the relevant report and create a Git commit before reporting
completion. Follow the workspace README's "工作记录与 Git 提交规则" section.
This device tree is tracked by the workspace-root Git repository. Sync changes
made in the WSL build tree back to the workspace and verify them before committing.

`BoardConfig.mk` and `device.mk` declare this device's platform, boot, partition,
kernel/module, HAL and product settings directly. There is no runtime inheritance
from another Xiaomi device tree. Properties, init/fstab, module lists, overlays,
VINTF, SELinux and extraction fixups are maintained in this directory.

The proprietary output is exclusively `vendor/xiaomi/sheng`, extracted from
the user's stock OS3.0.303.0.WNXCNXM firmware. The input firmware directory is
read-only; cached partition files and firmware are on C: inside WSL.

External source dependencies are the official LineageOS SM8550 kernel, modules,
devicetrees and `hardware/xiaomi`, plus normal Android/LineageOS/Qualcomm platform
repositories. The first kernel is 5.15; the 6.12 port is a later task.

For the initial source-kernel build candidate, the kernel core is built from the official
LineageOS 5.15 source. The vendor BSP uses the supplied firmware's complete
417-module set, pinned by SHA256 in `kernel/stock-modules/module-plan.json`.
ZRAM and zsmalloc are built from the current kernel source. Mixing the smaller
stock-only set with generic phone BSP modules was rejected by real CRC checks.
The staging guard validates every effective module before selecting the package
contents; it never edits module CRCs or vermagic. Boot and recovery module sets
come from this tablet's stock loading lists and actual ELF symbol dependencies.

Some generic Qualcomm init, platform policy and configuration sources were
adapted from the authorized official LineageOS sources. Their original notices
are retained. The migration receipt in the project reports records file hashes
and source commit; piano was used only to study organization, with zero copied
implementation files.

## Directory layout

The layout follows the [piano seventeen tree](https://github.com/xiaomi-pad-8-pro-development/android_device_xiaomi_piano/tree/seventeen),
fresh-fetched at commit `3f10fc25273b42d18d0bd533551a0a5c3dda0094`.
Its implementation files are not imported. sheng-specific adapters and development
tools are grouped below while the normal Android product entry points stay at the root.

| Directory | Contents |
| --- | --- |
| `aidl/` | Device AIDL services and declared interfaces. |
| `configs/` | Audio, display, input, sensor and VINTF configuration; display files use `configs/display/`. |
| `dolby/` | Dolby settings application. |
| `interfaces/` | Board-owned audio, display, compatibility and location adapters. |
| `interfaces/input/` | Keyboard and touch candidates; physical testing is currently paused. |
| `overlay/` | Framework, SystemUI and ROM resource overlays. |
| `properties/` | Partition-specific properties. |
| `rootdir/` | Init, fstab and their build modules. |
| `sepolicy/` | Integrated board policy. Candidate input policy stays with its feature until integration. |
| `kernel/`, `recovery/` | This board's kernel/module and Recovery configuration. |
| `tools/` | Source audits, build helpers, development packaging and diagnostic probes. |
| `docs/`, `patches/` | Current status, validation evidence and device-source derivation records. |

Root `Android.bp` keeps the namespace and firmware symlinks. Compatibility and
init modules live with their source directories. Production install paths and
module identities are retained when source directories move.

## Current validation

The tested device baseline is r11. Display, 144 Hz wake, touch direction,
automatic rotation, six-speaker audio, live Dolby controls, ambient brightness,
cover wake, model name and network location have recorded results in
[`docs/HARDWARE_STATUS.md`](docs/HARDWARE_STATUS.md). Each remaining item keeps
its own verification status; source and build success are recorded separately
from actual device testing.

The r12 generic fullscreen configuration compiled and passed its temporary
window test. Stock color-library registration is integrated as a candidate.
Keyboard/touch candidates are retained for the user's return and are not
registered in the current product. No runtime touch experiment is left active.

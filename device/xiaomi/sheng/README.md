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
417-module set, pinned by SHA256 in `interfaces/kernel/stock-modules/module-plan.json`.
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
Its implementation files are not imported. The tree has exactly ten top-level
directories. Board adapters and development tools are grouped below while the
normal Android product entry points stay at the root.

| Directory | Contents |
| --- | --- |
| `aidl/` | Device AIDL services and declared interfaces. |
| `configs/` | Audio, display, input, sensor and VINTF configuration; display files use `configs/display/`. |
| `dolby/` | Dolby settings application. |
| `docs/` | Current status, validation evidence and historical derivation diffs in `source-patches/`. |
| `interfaces/` | Board-owned audio, display, compatibility, location and kernel adapters. Input and SystemUI candidates remain unintegrated. |
| `overlay/` | Framework, SystemUI and ROM resource overlays. |
| `properties/` | Partition-specific properties. |
| `rootdir/` | Init, fstab and their build modules; standalone Recovery sources in `recovery/`. |
| `sepolicy/` | Integrated board policy. Candidate input policy stays with its feature until integration. |
| `tools/` | Source audits, build helpers, development packaging and diagnostic probes; local caches stay in `cache/` and are ignored by Git. |

Root `Android.bp` keeps the namespace and firmware symlinks. Compatibility and
init modules live with their source directories. Production install paths and
module identities are retained when source directories move.

## Current validation

The latest accepted runtime baseline is r23, as recorded in
[docs/HARDWARE_STATUS.md](docs/HARDWARE_STATUS.md). The user confirmed r22's
Douyin tablet adaptation and separate marketing-name row in Settings; the
numeric model remains 24018RPACC. The provider's factory-default name resources
passed 272 locale cases, without performing a factory reset. Battery SOH 93%
and normal picture/touch were accepted by the user.
Earlier the user confirmed normal picture/touch, no
brief yellow flash on wake/password entry with ambient white balance enabled,
and smooth Night Light activation. RGB and Night Light hardware color effects
were accepted on r15. Lift-to-wake is user-confirmed working. AON's existing
Screen attention failed the r19 gaze test; r23 restored its stock configuration
link and the user subsequently confirmed that AON works. Ordinary video and
speaker output were also confirmed after r23.
Details and remaining items are in [docs/HARDWARE_STATUS.md](docs/HARDWARE_STATUS.md).

r24 reached framework boot completion but SystemUI repeatedly crashed due to
instance fields lost by the device-owned APK transform. The accepted r22
system_ext and vbmeta_system were restored. The user confirmed reaching the
lock screen/launcher, all six partition hashes match and original SystemUI
remained stable during automatic checks. The user prohibits SystemUI changes;
the replacement module and transform tools are withdrawn. Power-button animation
is excluded from the repair target at the user's request. See
[docs/POWER_BUTTON_ANIMATION.md](docs/POWER_BUTTON_ANIMATION.md) and
[docs/r24-systemui-boot-regression-20261108.md](docs/r24-systemui-boot-regression-20261108.md).
r25's two independent
camera and Dolby GraphicBuffer allocation repairs passed the formal build,
binary review and local image validation; r25 has not been flashed. The later
stylus direction configs passed the platform parser, but a complete new product
build was interrupted by host C-drive pressure and they are not installed.
The compiled offscreen Dolby Vision regression is prepared for execution only
after r25 installation and basic runtime checks. See
[docs/offline-validation-20261108.json](docs/offline-validation-20261108.json)
for exact evidence hashes and validation boundaries. Local r25 image and pinned
decode-fixture validation were rerun successfully after that record was committed.
Those sealed r25 images were reviewed against the original r24 baseline;
preserve their guards until a supplemental review explicitly verifies the
restored upstream SystemUI partition chain.

The final color request keeps 自适应/生动/鲜艳 visible order and swaps the latter
two functions; r18 passed the user check and 鲜艳 selection reads actual mode1. Source/build/package milestones remain
separate from device acceptance. Keyboard and double-tap touch candidates stay
paused and unregistered in the current product.

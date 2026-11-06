# Xiaomi Pad 6S Pro 12.4 — sheng

Standalone LineageOS 24.0 device configuration for model **24018RPACC**.
The device codename is **sheng**; its board/firmware identifier is **N81A**.

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

The current checks cover input integrity, standalone references, scoped makefile
evaluation, extraction, module-guard behavior and overlay resource compilation.
Full Android compilation, private module compatibility and hardware boot testing
remain separate required validation steps.

The first full ROM compiled. The user's latest retest confirms the source kernel
boots with version5.15.220; the full Lineage ROM and Recovery display remain
unverified. Earlier broad failure reports were superseded by this retest. See the workspace report
`reports/recovery-bringup-20261105.md`. Recovery r2 is a separate self-contained
diagnostic image with our compiled Lineage recovery userspace and the exact
kernel/DTB/DTBO/modules extracted from the user's own stock firmware. Its
configuration is in `recovery/`; the main ROM's kernel strategy is not silently
changed to a stock prebuilt. Later r3/r4 serial diagnostics isolate Recovery
startup/display; full-ROM and peripheral validation remain required.

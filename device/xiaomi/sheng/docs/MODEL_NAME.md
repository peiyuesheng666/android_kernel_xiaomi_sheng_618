# sheng marketing name

Settings reads Build.MODEL. PRODUCT_MARKETNAME alone is not consumed by the
pinned upstream Settings/build implementation. The device's existing
TARGET_SYSTEM_PROP now provides `ro.product.model=Xiaomi Pad 6S Pro 12.4`.
PRODUCT_MODEL remains 24018RPACC, including the partition-scoped system/vendor
model and the vendor model used for attestation. No Settings, framework or
public build source was changed.

The normal hardware-build helper compiled system/build.prop successfully on
2026-11-07. Its fresh-fetch receipt is `upstream-model-name-build-audit.json`:
all 1,243 public repo-managed projects are clean and the 13 detailed source
checks passed. The generated model properties have both the marketing name
and the preserved scoped model. The temporary generated Soong memory wrapper
was restored to the original ELF after the build.

The optional r7 development packager pins the exact installed OTA system image
and r5 vbmeta_system, which r6 retained. The older build output and r2 child
AVB image are rejected because they do not match the installed base. r7 adds
only this property in /system/build.prop, preserves inode 667, its two allocated
blocks, permissions, owners, timestamps and every xattr, and changes only inode
size plus data in filesystem blocks 45, 77323 and 77324. All other filesystem
bytes are unchanged. Readback and read-only e2fsck pass; the original AVB salt,
metadata and every other descriptor are retained. Vendor/ODM/r6 display and
the r5 Dolby app are outside this delta.

The r7 system and vbmeta_system delta was flashed to slot b and booted. ADB
readback confirms `ro.product.model=Xiaomi Pad 6S Pro 12.4` while system,
vendor and ODM scoped models remain `24018RPACC`. The r6 vendor and vbmeta
hashes are retained, SurfaceFlinger reports actual 144 Hz, and boot completes.
On 2026-11-07 the user confirmed the correct name in Settings and normal display
and touch. Evidence is in `model-name-r7-validation.json`.

The flash guard reads system/vendor dynamic partitions through
`/dev/block/mapper`, verified on the running device, and physical AVB partitions
through `/dev/block/by-name`. Disconnected USB inventory is checked before any
blocking serial command during the Fastbootd transition.

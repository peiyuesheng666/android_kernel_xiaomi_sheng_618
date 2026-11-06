# sheng graphics startup

The stock KGSL driver probes asynchronously. Allocator and composer must wait
for `/dev/kgsl-3d0` before their gralloc helpers cache GPU alignment information.
The device-owned service modules retain the verified wait (up to ten seconds,
then fail for init to retry). They use unique sheng binary/RC filenames, the
original Binder interfaces and init service names, and exact original HAL
execution labels. This prevents duplicate installation rules from the public
service modules while preserving Android's service discovery.

The implementation sources and their upstream notices are under `display/`.
`SOURCE_BASELINES.json` and the historical diff record the upstream revision
and the two changed service entry points. The public display repository is
byte-identical to the freshly fetched upstream commit.

r2 boot exposed 144 Hz before framework refresh-rate overlays took effect.
At that mode SDM exhausted composition strategies and returned invalid present
fences; temporarily selecting the original 60 Hz config restored the display.
The r3 experiment selected the 60 Hz SDM config before the first commit.
System boot and sensor init succeeded, but the panel turned white/black until
an off/on cycle. This did not pass the display test. The stock kernel reports
continuous splash enabled, and Qualcomm's HWC requires the DRM preferred mode
for the first commit.

The correction retains the actual preferred boot mode (120 Hz on sheng) along
with native-resolution 60 Hz, preserving original IDs and the raw-config map.
It lets the normal HWC path defer the framework's 60 Hz request until after
the first commit. The 144 Hz mode is excluded, unadvertised switches are
rejected, and external displays are unchanged. The framework default and peak
remain 60 Hz. High-refresh support and this corrected cold boot still require
hardware testing.

`scripts/package_sheng_startup_followup.py` produces startup revisions from the verified r2
vendor and vbmeta bases. It packages only the compiled composer and both sensor
init configuration files, verifies every file and inode after EROFS readback,
and changes only vendor's AVB descriptor. ODM and system_ext remain at r2.

The observed one-to-two-second backlight interval during recovery/Android
startup remains a separate issue. This migration preserves the existing boot
fix; it does not claim to eliminate that interval. The device modules compiled
successfully and the images were flashed to slot b on 2026-11-06. Boot and
hardware regression checks remain pending while ADB is unavailable after reboot.

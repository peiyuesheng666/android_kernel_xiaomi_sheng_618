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
remain 60 Hz. The r4 reboot passed: the user saw a normal desktop without an
extra off/on cycle, and two cover close/open cycles displayed normally. The
active mode was 60 Hz, with no SurfaceFlinger backdoor override. High-refresh
support beyond this preferred-mode handoff remains a separate task.

After the r5 audio followup, DRM state confirmed the panel actually operating
at native 120 Hz. A framework 60 Hz request changed DRM to the native 60 Hz
timing, and returning to 120 Hz retained that timing after an off/on cycle.
The connector advertises 120/144/90/60/50/48/30 Hz. A device-owned diagnostic
switch, `vendor.display.sheng.native_modes`, exposes only native-resolution
60/90/120/144 configs and derives the HWC maximum from that advertised set.
Its default is false, preserving the verified boot/60 pair. It retains the
preferred first-commit handoff and raw config IDs. Enabling it requires a
composer restart. Native 90/144 Hz operation and sleep/wake remain unverified.

`scripts/package_sheng_startup_followup.py` produces startup revisions from the verified r2
vendor and vbmeta bases. It packages only the compiled composer and both sensor
init configuration files, verifies every file and inode after EROFS readback,
and changes only vendor's AVB descriptor. ODM and system_ext remain at r2.

The observed one-to-two-second backlight interval during recovery/Android
startup remains a separate issue. This migration preserves the existing boot
fix; it does not claim to eliminate that interval. The r4 startup delta was
flashed to slot b and boot-verified on 2026-11-07; both installed image hashes
matched the packaged images. Dolby live-control validation is tracked separately.

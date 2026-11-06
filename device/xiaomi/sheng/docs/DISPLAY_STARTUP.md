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
The device-owned composer now selects the native-resolution 60 Hz SDM config
before publishing a single supported built-in mode, retaining its original ID
and raw-config mapping. It rejects unadvertised mode switches and leaves
external displays unchanged. This is a safe bring-up restriction: high refresh
rates remain unverified and are not presented as fixed. Its first DRM commit,
boot and suspend/resume still require a rebuilt-image test.

`scripts/package_sheng_startup_followup.py` produces r3 from the verified r2
vendor and vbmeta bases. It packages only the compiled composer and both sensor
init configuration files, verifies every file and inode after EROFS readback,
and changes only vendor's AVB descriptor. ODM and system_ext remain at r2.

The observed one-to-two-second backlight interval during recovery/Android
startup remains a separate issue. This migration preserves the existing boot
fix; it does not claim to eliminate that interval. The device modules compiled
successfully and the images were flashed to slot b on 2026-11-06. Boot and
hardware regression checks remain pending while ADB is unavailable after reboot.

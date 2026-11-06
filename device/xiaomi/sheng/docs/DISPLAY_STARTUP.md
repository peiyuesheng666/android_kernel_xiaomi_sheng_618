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

The observed one-to-two-second backlight interval during recovery/Android
startup remains a separate issue. This migration preserves the existing boot
fix; it does not claim to eliminate that interval. The device-module rebuild
and flashed-image regression test are pending.

# piano reference scope

Compared with the user-specified `seventeen` tree at commit
`3f10fc25273b42d18d0bd533551a0a5c3dda0094` on 2026-11-06.

| Component | piano tree | sheng tree |
| --- | --- | --- |
| Sensors | Device-owned `aidl/sensors` service with an SM8750-specific binary/RC name | Device-owned multihal with a sheng binary/RC name and measured orientation correction |
| Display startup | Device-owned display boot script and RC modules | Device-owned allocator/composer entry points retain the KGSL readiness wait |
| PAL | Stock prebuilt; extraction adds `libaudioroute-xiaomi.so` to its dependencies | Device-compiled PAL supplies the six-speaker PCM/offload mapping; preferred installation matches the native device module's hash |
| Dolby UI | Platform-signed privileged `DolbyManager` in `system_ext`, replacing MusicFX/AudioFX | Platform-signed privileged `ShengDolby` with Settings entry and stock DMS controls |

Sources reviewed: `aidl/sensors/Android.bp`, `rootdir/Android.bp:172`,
`extract-files.py:237`, `dolby/DolbyManager/Android.bp`, and `device.mk`.
The reference establishes the organization and device-local integration
patterns visible in that tree. It does not establish the working-tree state
of all external repositories in the piano project or prove sheng hardware fixes.

The sheng PAL installation and six-speaker compatibility are sheng-specific
work, not an implementation copied from piano. Device-owned modules compiled
successfully and the validated images were flashed to slot b on 2026-11-06.
New-image boot and hardware validation remain pending while ADB is unavailable
after reboot.

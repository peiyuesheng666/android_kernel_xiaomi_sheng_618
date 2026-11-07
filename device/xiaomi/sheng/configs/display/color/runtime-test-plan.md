# Runtime validation and rollback

The current `/vendor` mount is read-only EROFS and the configuration target
does not exist. A file bind mount needs an existing target inode, so it cannot
inject this missing file without first providing a writable vendor layer.
Do not mask all of `/vendor/etc` with a temporary directory: its existing
submounts and file labels must remain valid.

The preferred coordinated test is to build this small prebuilt module and
include `/vendor/etc/snapdragon_color_libs_config.xml` and its required
`/vendor/etc/df_default.xml` in the next candidate vendor image derived from
the current r6 baseline. Rollback is the unchanged
r6 `vendor.img`, together with the existing boot/vbmeta flash procedure. No
display refresh setting or composer source change is part of this candidate.

If the coordinator already has a writable vendor overlay, a temporary test can
stage the same XML at
`/data/local/tmp/sheng-display-color/snapdragon_color_libs_config.xml`, verify its
SHA256 against `provenance.json`, and install it at the exact vendor target with
mode 0644 and SELinux context `u:object_r:vendor_configs_file:s0`. Record that the
target was originally absent. Do not disable verity or create a scratch
partition automatically to obtain this writable layer.

The init service is `vendor.qti.hardware.display.composer`. Its device-tree RC
declares `onrestart restart surfaceflinger`. Coordinate one service restart
with the other hardware tests; changing only `persist.sys.sf.color_mode` does
not reload the library initialization configuration.

Before and after the restart, read and compare:

- `sys.boot_completed`, compositor/service state, and the selected physical mode;
- supported color modes in `dumpsys display` and `dumpsys SurfaceFlinger`;
- the composer process maps for both registered libraries;
- STC initialization or calibration-path errors in the fresh display log;
- visible screen health and color-mode changes, verified by the user.

Expected evidence is that the two libraries load and calibrated sRGB / P3 modes
become available. The configuration and property declarations alone are not a
passing result. Check normal wake, cover wake and the existing refresh mode
without altering refresh settings.

For the writable-overlay test, rollback removes only the new configuration
after verifying its path and expected hash, then performs the same coordinated
composer restart. The original XML was absent; no existing configuration file
should be deleted. Keep the r6 vendor image available if the display cannot
recover. Leave the existing per-panel JSON and LUT files unchanged.

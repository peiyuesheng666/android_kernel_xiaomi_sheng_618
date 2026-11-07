# r13 display check

Run from the Windows workspace only after r13 is flashed and ADB is available.
These commands read state. They do not wake the display, set modes, restart
services, or start a camera/AON client. Permission errors mean unavailable
evidence; do not change device privileges or mounts to make this check pass.

```powershell
$adb = '.\tools\platform-tools\adb.exe'
& $adb -s ca10ede3 shell 'getprop sys.boot_completed; pidof vendor.qti.hardware.display.composer-service-sheng; sha256sum /vendor/etc/snapdragon_color_libs_config.xml /vendor/etc/df_default.xml /odm/etc/display/qdcm_calib_data_xiaomi_n81a_36_02_0a_vid_mode_duledsi_dsc_panel.json'
& $adb -s ca10ede3 shell 'p=$(pidof vendor.qti.hardware.display.composer-service-sheng); case "$p" in ""|*[!0-9]*) echo "Composer PID missing or ambiguous"; exit 1;; esac; cat /proc/$p/maps | toybox grep -E "libsnapdragoncolor-manager\.so|libsnapdragoncolor-qdcm\.so|libmi-stc-HW-modulate\.so"'
& $adb -s ca10ede3 shell 'dumpsys display | toybox grep -E "mDefaultDisplayDefaultColorMode=|mSupportedColorModes=|mActiveColorMode=|mRequestedColorMode=|mDisplayState=|mActiveModeId=|mActiveSfDisplayMode="; dumpsys SurfaceFlinger | toybox grep -E "Color modes:|ColorMode::|Current color mode:|colorMode=|activeMode=|activeColorMode" | head -n 24'
& $adb -s ca10ede3 shell 'cat /sys/kernel/debug/dri/0/state | toybox grep -E "crtc|enable=|active=|mode:"'
& $adb -s ca10ede3 shell 'p=$(pidof vendor.qti.hardware.display.composer-service-sheng); case "$p" in ""|*[!0-9]*) echo "Composer PID missing or ambiguous"; exit 1;; esac; logcat -d --pid=$p -v brief | toybox grep -iE "stc|qdcm|color|snapdragon|miXmlParser|dlopen|calib|error|failed" | tail -n 50'
```

Expected file SHA256 values:

| File | SHA256 |
| --- | --- |
| vendor Snapdragon Color XML | `dd41f581cbd151bfbfe92f1db1ee80ebc12ed8c21851790d770d30fb3e0c4dea` |
| vendor df_default XML | `f87d9367f7ca2a118bf512944619aaae8bc262fc2dcd629a895b2b3f0b9a74dc` |
| ODM panel QDCM JSON | `5eff4bb9342cf499c7bc313ded7dea5eae70977068fdb9aa0029a98ffe193b70` |

Record boot_completed=1, a live composer, all three mapped libraries, color
modes beyond Native (sRGB/Display P3), and initialization/calibration failures.
An empty log excerpt is not proof that initialization ran successfully.

Record the active CRTC mode's actual rate/timing and enable/active state. A
framework 144 Hz label or supported-mode list alone does not establish actual
144 Hz operation. If the display is OFF or DRM state is unavailable, leave the
physical-refresh result pending; do not switch the screen on for this check.
Keep the CRTC identifier with its mode; same-CRTC enable=1 and active=1 are
required. The recorded native 144 Hz DRM timing clock is 1040058 kHz; the stock
396906 kHz submode clock is a separate value (see `docs/DRM_SUBMODE.md`).

This check validates installation and available processing paths. Visible color
accuracy, white-balance calibration, and screen-off/wake behavior require their
separate user/instrument tests. Standard DWB remains disabled in this batch.

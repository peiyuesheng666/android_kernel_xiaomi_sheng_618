# Display color and ambient white balance

This is the initial pre-r13 investigation. r13 subsequently restored the color
plugins and sRGB/P3 enumeration. The user confirmed there is no visible color
cast but reported ineffective adjustments. The r14 hardware ABI and ambient
white-balance candidates, native XYZ evidence and current compile/acceptance
status are tracked in [LIVEDISPLAY.md](LIVEDISPLAY.md); the historical disabled
state below must not be read as the latest source configuration.

The current device exposes only Native color mode. The stock Snapdragon Color
manager is mapped into the composer, but its QDCM and Xiaomi STC plugins are not:
the installed vendor lacks `/vendor/etc/snapdragon_color_libs_config.xml`.
`configs/display/color` restores that exact stock file and the independently
required `df_default.xml`. Both need rebuilt-image validation; color accuracy
has not passed user or instrument testing.

The stock `libmiXmlParser.so` contains `vendor/etc/df_default.xml`. The stock
vendor and ODM copies both have SHA256
`f87d9367f7ca2a118bf512944619aaae8bc262fc2dcd629a895b2b3f0b9a74dc`, but only
the ODM path was listed by the generated vendor makefile. The new vendor
prebuilt has its own installation path and no existing install-rule conflict.
The STC plugins' additional dependencies, including tinyxml2_1, miXmlParser,
eyecare, qservice and stagefright_foundation, exist in vendor. The composer
already has read access to the panel-info sysfs type through Qualcomm's
`r_dir_file(hal_graphics_composer_default, sysfs_type)` and access to persist
display calibration. No extra SELinux rule or display-feature service is added.

## Standard DisplayWhiteBalance

Android 17's DisplayWhiteBalanceController already selects the front sensor
from the display configuration: `xiaomi.sensor.front_cct`, name
`stk_stk3bcx front CCT Cct Sensor Non-wakeup`, vendor type 33171088. The legacy
factory instead compares `getStringType()` against
`config_displayWhiteBalanceColorTemperatureSensorName`; the framework RRO now
sets that same exact type. Availability and default enablement remain unchanged.
Current `dumpsys color_display` reports `Not available`; the controller's sensor
listener and event buffers are inactive.

A bounded 15-second probe registered only that non-wakeup front CCT sensor. It
received one fresh 6382 K sample, accuracy 3, with a 7 ms event age, then
unregistered and exited normally. It did not observe a zero or nonfinite first
value. No HAL filtering change is included. The sensor's declared maxRange of
131.6 does not describe its valid Kelvin readings and must not be used to clamp
6382 K. Standard AmbientFilter only rejects values below zero, so any future
invalid-sample fix must preserve flush/additional-information events and other
sensor identities, and must have separate evidence and tests.

The standard path can implement ambient adaptation without an extra service or
private sensor permission, but the panel calibration is incomplete. It prefers
RGB primaries from SurfaceControl, falling back to 12 resource XYZ values. It
also needs a three-value nominal-white XYZ vector, nominal-white CCT, output
range, ambient-to-display CCT splines, and light-bias/filter/transition settings.
Night mode, color-accessibility transforms and unmanaged/nonlinear color modes
can suppress its activation. It runs only on the primary display while ON.

The stock panel XML has a TrueTone2 two-dimensional Lux/CCT target table,
LowLuxCCT 5600 K, and target limits 5300–8100 K. Standard DWB uses a one-dimensional
CCT spline plus light bias; copying the stock table directly would change its
meaning. Stock white-point entries such as `4095 4095 3920` are channel gains,
not XYZ. The stock CTA nativeCT of 7400 K and the framework nominal 6500 K are
also different. Actual primaries and the white point of each active color mode
must be verified before enabling the standard feature. No guessed calibration,
availability flag, mode write or DWB setting change is included.

## Upstream references

Paths are relative to `/root/sheng-lineage/lineage-24.0` and were read unchanged:

- `frameworks/base/services/core/java/com/android/server/display/whitebalance/DisplayWhiteBalanceFactory.java:181–204`: legacy string type and DDC sensor selection.
- `frameworks/base/services/core/java/com/android/server/display/DisplayPowerController.java:601–615,1744–1751,1816–1819`: primary display, enablement, and idle strong mode.
- `frameworks/base/services/core/java/com/android/server/display/color/ColorDisplayService.java:1024–1031`: activation restrictions.
- `frameworks/base/services/core/java/com/android/server/display/color/DisplayWhiteBalanceTintController.java:96–115,268–299,402–436`: primaries, nominal white, and Bradford transform.
- `frameworks/base/services/core/java/com/android/server/display/utils/AmbientFilter.java:75–84`: sample acceptance.
- `frameworks/base/core/res/res/values/config.xml:1009–1080,5749–5979`: standard resources and disabled defaults.
- `packages/apps/Settings/res/xml/display_settings.xml:195`: existing DWB preference.

This investigation used read-only ADB plus the separately authorized temperature
probe. No screenshot, camera/AON, display-mode or power-node change, compositor
restart, image build, or flash was performed.

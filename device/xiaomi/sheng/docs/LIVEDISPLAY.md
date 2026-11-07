# LiveDisplay and display color controls

2026-11-07 follow-up to r13. The user clarified that the panel has no visible
color cast. The remaining complaint concerns ineffective color options/sliders
and the automatic mode in the LiveDisplay page. Sensor-based TrueTone and
LiveDisplay's sunset/sunrise mode have separate activation paths.

## Standard color menu

The old device overlays advertised Xiaomi vendor intents 266/267/268/270 and
called framework mode 0 Saturated and mode 1 Standard. The unmodified
ColorDisplayManager defines 0 as Natural, 1 as Boosted and 2 as Saturated.
SurfaceFlinger treats the vendor range as vendor render intents, which this
composer does not advertise. Its actual HWC color spaces are Native (0),
sRGB (7) and Display P3 (9); those numbers are not settings mode identifiers.

Both overlays now agree on standard modes 0/1/2 and use Settings' existing
localized names. Every mode maps to composition color space 0, clearing a
previous forced gamut while retaining SurfaceFlinger's content-aware selection.
No invented sRGB-D65/vendor modes or Automatic render intent are advertised.

Source evidence in the pinned, unchanged ROM checkout:

- frameworks/base/core/java/android/hardware/display/ColorDisplayManager.java
- frameworks/base/services/core/java/com/android/server/display/color/DisplayTransformManager.java
- packages/apps/Settings/src/com/android/settings/display/ColorModeUtils.kt

## RGB control investigation

On the running r13 image a bounded Binder call through the same
ILiveDisplayService.setColorAdjustment used by the RGB dialog changed blue from
1.0 to 0.6. LiveDisplay reported [1.0, 1.0, 0.6], its hardware state was
[255, 255, 153], and SurfaceFlinger's final color matrix had a blue diagonal of
0.600. A finally block restored [1.0, 1.0, 1.0] and the identity matrix.
This verifies the framework request path, not a visible panel effect or the
dialog's touch handling. No screenshot or camera was used. Further panel/user
verification is required before calling the ineffective-slider complaint fixed.

## Validation status

Source changes are pending Android overlay compilation and image/reboot
acceptance. The r13 acceptance record remains an immutable account of r13;
it must not be used to claim these follow-up changes are installed.

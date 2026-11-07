# sheng stock display and status-bar geometry

The r10 device overlays restore selected geometry from the read-only sheng
OS3.0.303.0.WNXCNXM firmware dump. Public framework and SystemUI sources are
unchanged. Both modules keep their standard ODM overlay installation paths.

## Resource sources

| Stock source | Resource | Values |
| --- | --- | --- |
| product/overlay/DevicesAndroidOverlay.apk, static priority 1000, target android | rounded_corner_radius, _top, _bottom | 66px |
| Same framework overlay | status_bar_height_default, _portrait | 86px |
| Stock framework-res.apk | status_bar_height_landscape | Reference to portrait, resolving to 86px |
| product/overlay/DevicesOverlay.apk, static priority 1, target com.android.systemui | rounded_corner_content_padding | 45px default; 40px sw600dp-port |
| Same SystemUI overlay | status_bar_padding_top | 12px |
| system_ext/priv-app/MiuiSystemUI/MiuiSystemUI.apk | status_bar_padding_start | 4px default; 8dp land |
| Same SystemUI APK | status_bar_padding_end | 4px default; 8dp land and sw600dp |
| Same SystemUI APK | ongoing_appops_dot_min_padding | 0dp; privacy indicator remains enabled |
| Same SystemUI APK | status_bar_clock_starting_padding, _end_padding | 4dp, 0dp |
| Same SystemUI APK | status_bar_left_clock_starting_padding, _end_padding | 0dp, 2sp |

The defaults/anydpi stock overlay variants agree. Physical-pixel dimensions
remain in px, independent of user density changes. Portrait on this tablet
selects 40px content padding, 4px content start and 8dp content end. Landscape
selects 45px content padding and 8dp at both content ends. Icon start/end
padding already matches the stock 3dp/4dp, so it is not overridden.

## Upstream layout mapping

SystemUI's `StatusBarContentInsetsProvider` reads its own
`rounded_corner_content_padding`. With left-to-right layout, outer content
insets are `P` on the left and `max(P, minDotPadding)` on the right. The previous
resources resolved to P=0 and minDotPadding=20dp, before nested content padding,
which produced the visibly asymmetric status bar. Framework corner radius
does not derive the SystemUI content padding automatically.

Keep the stock content padding in the SystemUI overlay and retain framework
`rounded_corner_content_padding` at its existing value. The privacy dot remains
enabled; its 6dp diameter fits inside the 40/45px internal content inset at the
device's 400dpi density. Explicit 20dp
`status_bar_padding_without_rounded_corners` preserves the upstream fallback
on external displays after changing the internal minimum to the stock 0dp.

Upstream `status_bar.xml` and `Clock.onDensityOrFontScaleChanged` use different
clock-padding resource pairs. The device maps both pairs to the stock reload
values 4dp/0dp, so initial layout and configuration reload agree. This is an
explicit upstream-layout adaptation, rather than a claim that the stock
initial-layout pair was already 4dp/0dp.

The 12px top inset is installed with the stock 86px framework status-bar height.
Adding it alone to the previous height would reduce the icon content area.
The wider status-bar height changes app insets as expected.

## Boundaries and validation

The stock/current display-cutout paths are empty. No camera hole, simulated
cutout or camera-protection path is added. The shared stock framework overlay
also contains a 1080x2400 display shape; that shape is not the 3048x2032 sheng
panel geometry and is not imported. The working display/touch orientation is
preserved.

Build, resource-resolution and hardware-validation results are recorded in
`system-hardware-followup-r10.json` and `overlay-geometry-r10-validation.json`.
Until hardware validation is recorded, these source values are not a claim of
verified corner-mask alignment or portrait/landscape visual appearance.

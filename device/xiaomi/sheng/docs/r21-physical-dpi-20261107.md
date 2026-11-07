# Sheng panel physical DPI correction

The running r20 display reports 3048 x 2032 pixels, logical density 400,
smallest width 813 dp and physical DPI 29.414 x 29.425. SurfaceFlinger and
HWC agree on the erroneous physical values. This implies a 124.5-inch panel.

Read-only inspection of the stock active N81A panel device-tree properties
returned `00 00 0a 48` and `00 00 06 da`: 2632 and 1754. The active connector
lists 3048 x 2032 modes. The stock panel dimensions use tenths of millimetres;
the board DAL currently interprets the raw DRM integers as millimetres.

The device-owned DAL corrects only DSI + 3048 x 2032 + 2632 x 1754 to
263.2 x 175.4 mm, preserving fractional millimetres. Expected physical DPI
is 294.146 x 294.258 and the diagonal is 12.45 inches. Logical density,
resolution, refresh, color and all other connector tuples retain their
existing behavior. Stock DT and firmware are read-only inputs.

Douyin 41.0.0 already receives sw813dp / xlarge in fullscreen. Static
inspection of the installed, unmodified APK finds an additional Xiaomi/Redmi
classification condition in classes32.dex, X.16r4.LIZ: the tablet property
must be true AND ToolUtils.isMiui() must succeed. classes56.dex implements
isMiui() as Class.forName("miui.os.Build") with a cached result. Therefore
correcting physical DPI alone does not satisfy that vendor-specific check.
No app data, APK or vendor identity was changed during inspection.

The DAL and separate Settings marketing-name overlay are being compiled as
r21. Compilation, packaging and runtime validation are separate milestones;
this source change is not an app tablet-mode acceptance claim.

Raw read-only evidence: reports/device/r20-runtime/display-metrics.txt,
surfaceflinger-dpi.txt and aweme-base.apk. Disassembly stays outside the
source tree in /root/sheng-lineage/douyin-review-r21.

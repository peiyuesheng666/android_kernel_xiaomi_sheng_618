# Power-button animation: out of scope, original SystemUI required

On 2026-11-08 the user explicitly prohibited changing SystemUI and requested
investigation of other solutions. The r24 APK transform and its later corrected
candidate are withdrawn. Their source and tests remain recoverable in Git
history (3ead534 and earlier); they are removed from current module discovery.
device.mk no longer selects ShengSystemUI. The historical r24 flash tool refuses
-Flash. Do not re-enable APK transformations or add new SystemUI overlays for
this animation under the current instruction. Existing accepted geometry
overlays are retained without changes.

The device currently runs the accepted upstream SystemUI APK after restoring
r22 system_ext and vbmeta_system. User confirmation: “已进入锁屏或桌面”.
The live APK SHA256 matches the unchanged platform build input:
33017b0d59e28da5db3e089a98f49601de508228a012392ee2d04c82cda3ccb1.

## Available configuration and its limits

The pinned platform source contains one position dimension:
frameworks/base/packages/SystemUI/res/values/dimens.xml,
physical_power_button_center_screen_location_y (default 620px).
It supplies a coordinate along an assumed edge, not an edge selector or a pair
of physical coordinates. No corresponding side/edge resource was found in
SystemUI resources, framework resources, display service, Settings or Lineage SDK.

In PowerButtonReveal.setRevealAmountOnScrim (LightRevealScrim.kt), rotation NONE
fixes the center X coordinate at 1.05 * width, outside the right edge. This
device's button is at the left edge in its natural landscape orientation.
Changing powerButtonY can move the center vertically but cannot change that X
coordinate. Landscape/seascape branches also use fixed edges. Separately,
WakefulnessLifecycle.getPowerButtonOrigin chooses only portrait/landscape and
hardcodes the right/bottom edge. A single dimension does not correct both paths
for this hardware in all rotations.

The current device tree does not override that power-button dimension.
No substitute resource or system property has been applied. Changing global
display orientation would affect the complete display/input geometry and is
not an isolated animation repair. No implementation is proposed from that
unverified possibility. Disabling the animation or relabeling the wake reason
would not meet the requested origin behavior.

The user subsequently stated that this animation does not count as a bug and
requested work on other issues. It is removed from the active repair list.
No further animation changes are planned under the current instruction.
Source correction/build receipts from the previous approach are historical,
not authorization to install it or evidence of animation acceptance.

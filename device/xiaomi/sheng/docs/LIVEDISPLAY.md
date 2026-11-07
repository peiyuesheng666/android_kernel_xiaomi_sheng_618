# LiveDisplay and display color controls

2026-11-07 label follow-up: the user requests 自适应 / 鲜艳 / 生动. The first
label replaces 专业原色 and the last two choices change order together with
their values. The Settings list is [0,2,1], preserving each mode's behavior
and saved numeric setting. 自适应 labels the existing managed/content-aware
mode 0; ambient color adaptation still uses the separate 显示屏白平衡 switch.
This device-only Settings RRO change is built/published after the r16 sensor
and neutral-white batch, whose frozen artifacts remain unchanged.

Latest acceptance: r14 failed composer initialization and was reverted to the
verified r13 images. The user confirmed normal picture/touch after recovery.
The corrected owning adapter subsequently passed a bounded temporary hardware
trial: RGB blue=0.6 produced a real PCC blob and the user confirmed visible
yellowing. This is runtime candidate evidence, not a persistent installation.
See [r14-boot-failure-20261107.md](r14-boot-failure-20261107.md). The byte-only
adapter's passing host test did not validate real container traversal/lifetime;
its raw borrowed-pointer approach is rejected. Candidate descriptions below
are development history, not claims that these features passed on hardware.

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

The framework advertises standard modes 0/1/2. Per the user's requested labels,
the Settings overlay names them 专业原色 / 生动 / 鲜艳 in Chinese and provides
local English strings. Its three values match that framework list; local
resources avoid unresolved target-only references when the standalone RRO links. Every
mode maps to composition color space 0, clearing a
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

The user reproduced no visible change from the dialog and also reported that
Night Light has no effect. The user requires hardware composition throughout.
The proposed GPU fallback was withdrawn before compilation or installation;
both composer methods remain identical to the committed r13 implementation.

Current composer logs repeatedly report ConvertDitherToPPFeature error 7 and
UpdateModeHwassets failure. Comparing the source-built and stock libsdmcore
PPHWAttributes::Set implementations gives an exact eight-byte layout difference:
the current HWResourceInfo ends at 0x268, while the stock color implementation
expects its suffix at 0x260. The source's trailing ddr_version is at 0x260.
The PP version array is at source offset 0x550 versus stock offset 0x548;
dpps_intf is at 0x578 versus 0x570. This can make the stock converter read the
wrong hardware feature version even though the matrix request succeeded.

A device-owned snapshot of the pinned SDM core adds a borrowed byte view only
at CreateColorInterface. It drops that DDR field and its padding, retaining the
complete old prefix and shifting the panel/configuration/version suffix by
eight bytes. The original source object retains ownership of its vectors/maps;
the byte view has no C++ container destructor. Static assertions guard all
relevant source sizes/offsets. All other SDM calls use the upstream layout,
and the stock color library and hardware composition capabilities stay intact.
The preferred device module installs the compiled library as libsdmcore.so.
This remains a hypothesis pending Android compilation and actual hardware tests.

The host ABI test executes the actual packing helper with address/undefined
behavior sanitizers and checks all nine versions, dither=7, the borrowed Dpps
pointer, brightness, the complete copied regions and unchanged input bytes.

## Validation status

The final r14 changes passed Android compilation; image/reboot and physical
acceptance remain pending. The r13 acceptance record remains an immutable account of r13;
it must not be used to claim these follow-up changes are installed.

## LiveDisplay, Night Light and automatic color temperature

The running r13 service has only capabilities 13 (RGB adjustment) and 18
(reading enhancement), and no temperature modes. The upstream
ColorTemperatureController requires !mNightDisplayAvailable, even though this
device already exposes the accelerated RGB calibration path. Android's default
config_nightDisplayAvailable=true therefore suppresses LiveDisplay temperature
control by design.

After the user explicitly reported the existing Night Light failure and
provided the sensor-based ColorOS reference, the initial LiveDisplay twilight
selection was superseded before installation. The final overlay retains
config_nightDisplayAvailable=true, preserving Night Light and its schedule.
LiveDisplay continues to provide RGB/reading controls. Its separate twilight
modes remain intentionally suppressed by the unmodified upstream service.
Actual environmental adaptation uses standard DisplayWhiteBalance below.
This preserves the requested existing night control and does not mislabel a
sunset schedule as sensor adaptation. No service fork, new HAL, polling,
boot-time setting write or private Xiaomi display service is added.

Compile FrameworkResOverlaySheng and SettingsResOverlaySheng together. After
installation/reboot verify resource lookup, LiveDisplay RGB/reading controls,
Night Light temperature changes and the final compositor matrix, then restore
the user's chosen settings. Verify that screen-off/on, RGB controls and color
mode changes still work. Visible panel response requires user acceptance.

## r14 packaging scope

The dedicated r14 packer pins all six installed r13/r9 image hashes. Only
FrameworkResOverlaySheng.apk and SettingsResOverlaySheng.apk change in ODM;
only lib64/libsdmcore.so changes in vendor. It reuses the verified r13 EROFS,
metadata, APK certificate, AVB parent and whole-directory publication helpers.
All tracked non-document device inputs, exact installed build outputs and
packaging inputs are frozen and rechecked before final publication. System,
system_ext and vbmeta_system remain untouched. No slot change or data erase.

## User-provided ColorOS reference

Read-only archive: E:/6/玩机资源/修复方案/ColorOS17环境色温修复.zip
SHA256: f8601c966a682b1346b7488bf3b4b1135150019b32e1702d5239917932568a4b.
No archive script, payload, framework JAR or camera/AON component was executed
or installed. Its record describes adapting ColorOS' CCT consumer to Xiaomi's
33171089 streaming sensor, with Kelvin at index 0 and lux at index 1. It also
records user-visible changes with stock SDM and forced GPU disabled. Those are
reference results for another ROM, not acceptance of this Lineage candidate.

## Build and packaging checkpoints

The initial two-overlay compilation completed successfully in 12:22. Subsequent
user label refinements, ambient white balance and the hardware-only SDM ABI
change passed a second targeted build in 15:11. ELF checking and preferred
device-core installation passed; image/reboot and hardware acceptance remain pending.
Both build entries perform the required fresh upstream audit. The ABI host test
passed with address and undefined-behavior sanitizers. The unchanged filesystem
helpers passed 12 cases; Linux publication passed 7 with 5 Windows-only skips.
The copied upstream core files retain their original whitespace, including six
files with an extra trailing blank line; modifications use clean whitespace.
Native Android clang record-layout checking confirmed the guarded 0x260 DDR
offset, 0x268 resource size and 0x550 PP version offset. It also found two
inherited discarded all_of results rejected by the current libc++ headers;
the device snapshot replaces those deletion-only calls with explicit cleanup
loops. The public source remains unchanged; the complete targeted Android build passed.

`tools/package_sheng_livedisplay.py --freeze-only` freezes the scoped outputs;
`--validate-only` rechecks them without creating images. Normal invocation
publishes the complete three-image batch only after metadata/readback and AVB
checks. `tools/flash_sheng_livedisplay.ps1` defaults to native local verification;
explicit `-Flash` additionally checks all six installed hashes, serial, model,
slot b and fastbootd identity before writing ODM, vendor and their vbmeta parent.
The USB runner and time limits are reused from the reviewed r13 flash tool.

## Sensor-based ambient white balance candidate

The read-only AIDL probe obtained the actual primary display token and native
XYZ values: R=(0.4123,0.2126,0.0193), G=(0.3576,0.7152,0.1192),
B=(0.1805,0.0722,0.9506), W=(0.9505,1,1.0891). They agree with the active
sRGB/D65 working-space contract. These API values are not new instrument
measurements. The standard DWB overlay now uses the returned white and matching
fallback primaries, nominal/default 6500 K, the panel's stock 5300-8100 K bounds
and 5600 K low-light target. Low-light blending covers 0-50 lux using the stock
CCT lux threshold. Native-primary evidence is retained as
reports/device/r14-display-investigation/native-primaries-before.txt.

Availability and default enablement are on, while an explicitly saved user
setting remains authoritative. DWB uses the verified 33171088 front Kelvin
sensor plus the standard ALS; unlike ColorOS' fused consumer it does not need
the streaming sensor's lux at index 1. No global sensor remapping is added.
Android's existing filter, throttling and Bradford transform handle adaptation
and suspend sensor listening when the primary display is off. The panel's 2D
stock table is not copied into an incompatible 1D resource; this is standard
Android ambient adaptation, not a claim of identical stock TrueTone2 mapping.

The existing standard DWB toggle controls real ambient adaptation; Night Light
controls the independent manual/night schedule. Framework restrictions
still apply: DWB is inactive during Night Light, in unmanaged Saturated mode and while conflicting
accessibility transforms are active. The managed Original/Vivid modes must be
used for its acceptance. This newly enabled path still needs real sensor,
matrix, hardware-composition, off/on and user-visible acceptance on r14.

## Read-only hardware color probe

After sealing the r14 batch, tools/ShengDrmColorProbe.c was added solely as a
diagnostic, outside that batch's immutable inputs. It opens /dev/dri/card0 with
O_RDONLY and issues only GETRESOURCES, OBJ_GETPROPERTIES, GETPROPERTY and
GETPROPBLOB. It prints CRTC activity/color property values and raw PCC words;
it never maps or reads pixels, acquires DRM master, sets a property or modesets.
Counts, allocation sizes, blob sizes and retries are bounded. Compile validation
uses the existing cross compiler with -static -O2 -Wall -Wextra -Werror and
external/libdrm/include/drm. Actual device readback on recovered r13 succeeds
after clearing unused GETRESOURCES framebuffer/connector/encoder counts before
the second ioctl. No pointers for those unused arrays are supplied. The
baseline has zero PCC and gamut blobs; the corrected library trial produces
nonzero blobs.

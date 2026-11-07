# Hardware followups after the r6 display batch

User requests received on 2026-11-07. These are pending integrations, not
claims of working features. Finish the current display flash/reboot validation
before changing another hardware path. All implementation remains in this
device tree; public repositories remain at freshly verified manifest revisions.

## Ambient color adaptation

The user confirms the stock OS supports this feature. Prior light testing
observed valid front-CCT data; the existing DisplayDeviceConfig selects
`xiaomi.sensor.front_cct`. Stock ODM's
`mdss_dsi_n81a_36_02_0a_duledsi_dsc_vid_mi.xml` enables TrueTone2 and contains
lux/CCT calibration, including a 5300-8100 K target range. Its xy chromaticity
coordinates must not be copied directly into an XYZ primary matrix.

The unmodified Android framework already has display white-balance control
and Settings support. A device RRO can enable availability and select the
front-CCT type for both the legacy and DisplayDeviceConfig paths. Verify native
display primaries and appropriate temperature/filter/low-light bias first.
The sensor may return 0 in low light; Android's ambient filter only rejects
negative values, so the device sensor path must reject invalid CCT readings.
Standard Android's one-dimensional mapping is not equivalent to the stock
two-dimensional TrueTone calibration. Exact stock behavior needs a separate
review of Xiaomi's missing DisplayFeature service and dependencies.

## AON screen attention

The user confirms AON support. Stock product's `MiAONService.apk`, package
`com.xiaomi.aon` version 1.0.90, exports `AonAttentionService` with the standard
AttentionService intent and BIND_ATTENTION_SERVICE permission. Its DEX includes
the Xiaomi AON AIDL client. The native AON implementation/models and QTI AON
HIDL 1.0-1.3 libraries are present in the current vendor inputs/build.

Missing integration includes the APK in the proprietary extraction list,
platform signing, its VINTF declaration, the framework attention-service
resource, and SELinux service lookup/registration mappings. Camera/CamX,
gralloc and QSEE backend availability and final installed CAMERA permission
must be verified. Do not advertise successful attention detection from APK
presence alone. No camera, image capture, or AON activation was performed in
this investigation; preserve the user's no-capture instruction.

## About-device marketing name

The required marketing name is `Xiaomi Pad 6S Pro 12.4` in
`ro.product.marketname`; the global `ro.product.model` and partition-scoped
hardware models must remain `24018RPACC`. PRODUCT_MARKETNAME alone does not
emit the required runtime property in this build. The earlier r7 global model
override was incorrect: the user reports that some applications no longer
recognize the tablet. r20 explicitly sets both properties in system.prop.
Compiled output, fresh upstream audits and r20 installed property/partition
readback pass; the user still reports affected-application failures. Settings displaying
Build.MODEL does not justify replacing the app-visible hardware model.

## Automatic screen timeout

The initial readback was 600000 ms (ten minutes), with charging-stay-awake
setting 2 but `mStayOn=false`. During the display test the setting changed to
15000 ms. PowerManager subsequently recorded `mLastSleepReason=timeout` and
DRM active=0, followed by successful wake at 144 Hz. There were no screen wake
locks in the inspected snapshot. This confirms the observed timeout path,
not all app- or charger-specific behavior. Do not force a timeout on each boot
or override the user's chosen setting.

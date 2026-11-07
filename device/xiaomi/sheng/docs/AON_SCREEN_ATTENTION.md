# sheng AON screen attention integration

Current candidate: restore the stock system application and exact native AIDL
service identity while using Android's existing 屏幕感知 / Screen attention
switch in Display / Screen timeout. Adaptive sleep remains absent/default OFF;
no camera, proximity or rotation setting is enabled automatically. Keyboard
and double-tap candidates remain paused. All changes are device-owned.

## Read-only evidence

Stock product/app/MiAONService/MiAONService.apk is com.xiaomi.aon 1.0.90, target
API33 and shared android.uid.system. SHA256: 63216e568b5b41b7213989ab930c2bf39a8529d9a6a2be7db99275284c443ac4. The manifest has no boot
receiver and does not mark the application persistent. AonAttentionService
exports android.service.attention.AttentionService protected by
android.permission.BIND_ATTENTION_SERVICE. It has no native APK libraries;
classes.dex is 119956 bytes and includes the Xiaomi AON AIDL client.
AonApplication/onCreate and the sheng AONFaceEnpu constructor only initialize
objects; listener registration/actual detection is in onCheckAttention.
sheng uses Enpu / vendor.xiaomi.hardware.aon.IAlwaysOn/miaonservicehal, not
another board's Tee backend. The app is to be platform re-signed for its system
shared UID. Its declared permissions are WAKE_LOCK and an optional MIUI analytics
permission. Installed CAMERA permission must be checked before switch testing.

The installed camera provider attempts to add that exact Binder name but is
rejected against default_android_service. Stock ODM supplies AIDL version1;
stock vendor_service_contexts maps the instance to hal_camera_aon_service.
The device declaration and label were missing. Device SELinux now assigns a
protected HAL service type and its existing camera server registration macros,
plus named-service lookup and callback Binder access for system_app.
No permissive domain, generic default-service allow or ordinary app access.

The retained boot trace has debuggerd signal35 from CamX NotifyResult/StreamOn
and CHXUsecaseAON.Initialize. The same provider PID1468 remains live, so this
is a timeout/debug stack, not proof of a SIGSEGV crash. media.camera reports
nine devices and no active public clients. Backend detection remains untested.
Raw evidence: workspace reports/device/r18-runtime/aon-inventory-log.txt,
crash-backends-for-aon.txt and camera-inventory-for-aon.txt. Static DEX review
is in /root/sheng-lineage/aon-review-20261107, with stock input unchanged.

## Integration and limits

The proprietary extraction list relocates only this APK to system_ext/app;
standard extract-utils uses the platform certificate. The extraction hook's
postprocess import is corrected from the removed scripts directory to tools.
A section-limited, no-cleanup extraction must retain existing vendor inputs.
Framework resources select the package and expose the existing switch; they
do not change the saved adaptive_sleep key or standard default0. Build, exact
signing/permission checks, immutable packaging, reboot and physical attention
acceptance are distinct steps. No checkAttention/startAttention/AON trigger,
camera launch, screenshot or image capture is used by the agent. After the
service is installed and ready, the user controls physical switch testing.

## Android 17 component resolution and extraction

The pinned PackageManagerService.getPackageFromComponentString requires a
flattened component, not a bare package. config_defaultAttentionService is
therefore com.xiaomi.aon/com.xiaomi.aon.AonAttentionService; PackageManager then
extracts and validates the installed system package. AttentionManager resolves
its standard intent and BIND_ATTENTION_SERVICE protection without running checks.

Section-limited extraction with --no-cleanup succeeded. The generated vendor
module is MiAONService, system_ext_specific=true, certificate=platform,
dex_preopt.enabled=false. The source APK is byte-identical to stock (131486
bytes, SHA256 recorded above). Existing vendor inputs and the device GSL/Dolby
postprocessing remain preserved. The proprietary source and generated recipe
are generated inputs; implementation stays in this device tree.

## r19 installed result: function still failing

All six partitions match after boot. The standard attention service, native
AON Binder, installed component and CAMERA permission are present. The user
can enable the existing switch but reports that the screen still times out.
The request reaches AonAttentionService and AONFaceEnpu; listener registration
and QSEE FD subscription acknowledge success, but no detection callback arrives
before cancellation. This is not an accepted attention implementation. No
agent-initiated detection or image capture was used; logs are from user testing.

## r20 native initialization failure narrowed down

Reading the existing CamX offline text log reveals a failure before any Java
attention check: QSEEAONControl registers successfully, but the firmware's
ProcessAONCamInitAck returns `Init failed error: 1`. SendAONCamInit fails for
`aon_front`, AONNodePostPipelineCreate fails, and AONPipeline finalization and
StreamOn fail. The subsequent signal35 stack is the provider's diagnostic
dump. This supports investigating native sensor/firmware initialization rather
than treating successful listener registration as functional detection. The
specific cause of firmware error1 remains unproven.

The firmware still reports basic/pro FD algorithm modes, and the later
FD-algorithm subscription can succeed despite the failed image pipeline.
Both installed aon_front.pb copies are 8983 bytes with SHA256
`b0d920c16e4968173cf8f4f90c1056e959b9aad1c2651a76cca17ee19dac46d6`.
The existing qsh_camera sensor registry is present. These checks do not prove
successful sensor initialization. No runtime restart, capture or detection
request was issued. Raw text evidence: reports/device/r20-runtime/
aon-native-offline.txt and aon-sensor-registry.txt.

## r21 preparation: firmware comparison, no firmware changes

Read-only comparison against the OS3.0.303.0.WNXCNXM input found 44 of 64
mounted ADSP-related files identical and 20 different. Both builds advertise
ADSP.HT.5.8-01106.6-KAILUA-1; the source OEM identifier is
pangu-build-bp-143180-svtcc-fhv62-g606g, while the live image identifies as
pangu-build-bp-155631-8xlmw-k2p5b-5663z. Timestamps and whole-partition hashes
alone were not used to establish this result. The compared DSP filesystem
contains 79 files; 78 match, with only adsp/sns_tppe.so differing.

These differences do not establish the cause of QSEE camera-init error1.
No firmware partition, sensor registry, camera provider or attention setting
was changed. The existing user choice remains adaptive_sleep=1 and timeout
15000 ms. No attention request, camera launch or image capture was initiated.
Raw file comparisons and version evidence are under workspace
reports/device/r20-runtime/aon-{adsp,dsp}-file-comparison.json and
aon-firmware-version.txt; the loaded OEM version was independently read from
the live adsp.b08 segment.

USB investigation is paused at the user's request. The user identified one
disappearance as a manual unplug/reboot and later suspected a loose cable.
The subsequent short disconnect during this comparison was caused by the
agent's adb root command restarting adbd, not an observed spontaneous failure.
Future adb root commands must be announced before execution.

## r23 preparation: missing stock vendor sensor alias

The offline stock vendor/lib64/camera/aon_front.pb is an absolute symlink to
/odm/lib64/camera/aon_front.pb. The original extraction list keeps both ODM
protobuf copies but omits this vendor symlink. The installed r22 vendor path
does not exist. A device-owned install_symlink restores the exact stock path
and target, without changing protobuf contents, firmware or sensor registry.
The target SHA256 remains b0d920c16e4968173cf8f4f90c1056e959b9aad1c2651a76cca17ee19dac46d6.

The ADSP consumer confirms this is a required lookup path: adsp.b33 contains
`/vendor/lib64/camera/%s.pb`. That 33684-byte segment is byte-identical between
the offline stock input and the currently loaded firmware, SHA256
af4f8ddda37c51ed1aa103b83e30b9579404db2331f21d66d3cf6ad074de958a.
The pathname omission is therefore directly relevant to the firmware lookup,
not inferred from an unrelated warning. Existing r22 logs still show firmware
init error1. Acceptance requires the installed link and target hash, a new boot
trace without that pipeline failure, and the user's physical attention test.
No camera/provider restart or attention request is issued for investigation.
Raw string evidence: reports/device/r23-investigation/aon-firmware-strings.txt;
live/stock segment identity: reports/device/r20-runtime/aon-adsp-file-comparison.json.

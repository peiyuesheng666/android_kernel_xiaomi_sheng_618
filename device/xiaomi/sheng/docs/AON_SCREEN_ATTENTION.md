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

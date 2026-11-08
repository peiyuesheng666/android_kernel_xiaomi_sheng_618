# Face enrollment requires HAL-owned preview

The user's r33 enrollment attempt reached FaceEnrollClient at 04:43:28.105
(device log timestamp). One millisecond later it returned framework error 2,
without either face daemon dying. A challenge had completed successfully.

The installed Settings resource config_face_enroll_hal_owns_camera resolves
to false. In the pinned upstream Settings implementation, that branch starts
enrollment without waiting for the HAL preview Surface; the returned preview
is null. The existing true branch waits for Surface readiness, passes it to
FaceEnrollSidecar and leaves camera ownership to the HAL.

The original sheng frontend's GNU debug symbols identify Session::enroll at
0x83e4 and enrollWithContext at 0x9ce4. The latter forwards to the former.
At 0x8488 the frontend checks the optional NativeHandle presence; the absent
branch 0x86a8 calls onError(2, 0) at 0x86d4 before invoking the HIDL enrollment.
This matches the observed immediate failure. MiSecureCamera::openCamera calls
AImageReader_newWithUsage at 0x103e4 with 640x480 YUV_420_888.

Enable the existing upstream HAL-owned mode and select a 640x480 preview in
the device's Settings RRO. No public source, face executable, security strength,
authentication token check, lockscreen or SystemUI is modified. This removes
the identified null-preview blocker; further camera, secure-world or enrollment
failures must be diagnosed from the next actual attempt. Build and runtime
acceptance are pending.

Raw evidence: reports/device/r33-face-failure-20261108 and WSL
/root/sheng-lineage/hardware-diagnostics/r33-face-aidl-disassembly.txt.

## Built and installed candidate

Scoped overlay compilation, signing and enforced host/device idmap checks passed.
Two real-device locale probes verified HAL-owned 640x480 preview and preserved
identity/color resources. Only resources.arsc differs inside the APK. Fresh
pre/post audits passed for 21 public repositories and 1243 project statuses.
ODM packaging changed only SettingsResOverlaySheng.apk; metadata, filesystem
UUID, AVB signature and other descriptors passed verification. All seven live
r33 partition hashes and original SystemUI were checked before writing odm_b
and vbmeta_b. r34 was written and rebooted; actual postboot readback and user
enrollment/authentication are still pending. Full product build has not passed.

Build: r34-face-preview-build-review-20261108.json; package: r34-packaging-20261108.json.
Flash operations: reports/device/r34-20261108-125225.

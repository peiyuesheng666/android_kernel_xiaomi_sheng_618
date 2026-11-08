# Face camera callback permission

The user's r34 attempt still failed, but its logs confirm a different stage:
FaceEnrollClient obtained preview handles, the AIDL frontend forwarded the
authentication token/features and the HIDL implementation entered enroll_start.
At 04:55:43.311 and .335, cameraserver calls to hal_miface_default were denied
by Enforcing SELinux. Camera conversion could not obtain the HIDL buffer queue,
capture-session stream creation failed and the face frontend reported error 1.
Both face daemons remained alive. r34's null-preview fix reached the next stage;
it did not establish working enrollment.

The existing binder_call(hal_miface_default, cameraserver) grants forward
call/transfer and reverse transfer, but not reverse call. Grant only the missing
cameraserver-to-miface Binder call for camera/session and buffer-queue callbacks.
No fd permission, domain membership, new type or permissive domain is added.
Build, exact compiled-policy difference and runtime acceptance remain pending.

Evidence: reports/device/r34-face-runtime-20261108/logcat-after-attempt.txt and
dmesg-after-attempt.txt. Seven r34 partition hashes, the installed overlay and
all three face resource values passed guarded postboot readback in
reports/device/r34-20261108-125447. User enrollment remained unsuccessful.

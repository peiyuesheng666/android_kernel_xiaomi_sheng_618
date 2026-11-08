# Face enrollment: missing service registration

Offline inspection on 2026-11-08 compared the verified current r30 ODM image
with the original sheng firmware. r31 changes only vendor and vbmeta, so the
ODM evidence also describes the unchanged ODM selected for that batch.

The original firmware includes these files, all absent from r30 ODM:

- bin/hw/android.hardware.biometrics.face-aidl-service
- bin/mifaced@1.0
- etc/init/android.hardware.biometrics.face-aidl-service.rc
- etc/init/vendor.xiaomi.hardware.miface@1.0-service.rc
- etc/vintf/manifest/face-default.xml

The original VINTF fragment registers android.hardware.biometrics.face version 2,
IFace/default. The two original init services are vendor.face-default and
vendor.miface-hal-1-0. The generated vendor tree already retains libmiface and
vendor.xiaomi.hardware.miface@1.0, but not these service binaries or registrations.
Having their client libraries is insufficient to provide the standard face HAL.

The AIDL service depends on face-V2-ndk, biometrics.common-V2-ndk, and the Xiaomi
miface interface. The mifaced daemon also depends on libmiface, vendor camera
and media NDK libraries, libQSEEComAPI, legacy graphics interfaces and libmisight.
Check every dependency against current installed ABI and SELinux policy before
adding either daemon. Preserve the original executables and add any integration
only within this device tree; a VINTF declaration alone cannot repair enrollment.

Disassembly inspection found GraphicBuffer::getNativeBuffer calls on buffers
obtained from AImage_getHardwareBuffer. It did not establish a legacy-sized
GraphicBuffer construction allocation needing the r25 fix; do not patch guessed
allocation sizes or treat this limited inspection as full ABI certification.

Evidence and original file hashes:
reports/device/r31-20261108-104747/face-offline-investigation.json and
libmiface-disassembly.txt. The ODM hash is
eecbef1b87f4055f5c35c519d2d1d220b479e0fe6320d970708e277ebba532c0.

This is investigation evidence. No face service or camera was started, no
enrollment or authentication was attempted, and no face repair is yet claimed.

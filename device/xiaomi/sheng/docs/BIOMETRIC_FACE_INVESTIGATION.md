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

The service also needs android.hardware.biometrics.face-V2-ndk.so and
android.hardware.biometrics.common-V2-ndk.so. Both original libraries exist in
the firmware inputs and are absent from the currently installed product trees.
The current public interface definitions retain frozen V2 source versions; an
integration should use these existing module names and verify the generated V2
libraries rather than creating conflicting replacements for shared interfaces.

A host ELF dependency check has now passed for both original service binaries,
both original V2 interface libraries, and the currently installed libmiface.
The dependency set combines current vendor libraries, current vendor variants
of LLNDK/runtime providers, and the two original V2 libraries as explicit
candidates. No DT_NEEDED provider was missing from that candidate set and no
undefined symbol was reported by check_elf_file.py. This is a candidate linking
check: the two V2 files are still absent on the device, generated V2 build outputs
have not been compiled, and linker namespaces, service startup and runtime ABI
behavior remain unverified. It does not establish a working face service.

Commands, exact provider paths, source hashes and all five zero exit statuses
are saved in reports/device/r31-20261108-104747/face-dependency-elf-check.json.

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

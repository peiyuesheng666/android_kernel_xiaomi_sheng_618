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
check: at that stage the two V2 files were absent on the device and generated V2
outputs had not been compiled. Linker namespaces, service startup and runtime ABI
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

## Frozen V2 source candidate build

Both V2 NDK interface libraries have now been generated from the unchanged public
frozen V2 AIDL definitions and compiled as isolated candidates. The device-owned
builder reuses recorded vendor compiler/linker templates by streaming Ninja text;
it does not load the complete build graph or install outputs into the product.
Fresh upstream audits before and after this build passed for 22 public repositories,
including hardware/interfaces, with all 1243 project statuses clean.

Both original service executables, rebuilt face V2, rebuilt common V2 and current
libmiface passed check_elf_file.py against the complete candidate dependency set.
The first face V2 ELF check omitted libnativewindow from its supplied provider
list and failed. The rebuilt library actually declares that dependency; adding the
existing current vendor provider to the check resolved it. Both the failed initial
report and the complete passing report are retained without disabling ELF checks.

Exact inputs, output hashes, command logs and audit hashes are recorded in
face-v2-candidate-build-20261108.json. These libraries remain uninstalled. Normal
product module integration, precise SELinux policy, service registration, linker
namespace behavior and runtime ABI still require validation. No service, camera,
enrollment or authentication was started by this candidate build.

## Device-tree service integration candidate

The device tree now contains both original executables, their unchanged init
scripts and both required VINTF fragments. Further inspection found a sixth
missing original file: vendor/etc/vintf/manifest/manifest_vendor.xiaomi.hardware.miface.xml.
It declares vendor.xiaomi.hardware.miface@1.0::IMiFace/default. The AIDL frontend
declaration alone does not register that HIDL implementation.

Device-owned cc_prebuilt_binary modules install both executables under their
original ODM paths, declare every non-default DT_NEEDED dependency and depend on
the existing public frozen V2 modules. The original HIDL fragment is attached to
the ODM implementation module; the combined device manifest includes both HALs.
The standard face feature XML is installed from unchanged framework data.
All six original files are pinned by interfaces/biometrics/face/SOURCE_SHA256.json.

The standard hal_face_default domain consumes a protected Xiaomi miface
hwservice in a separate hal_miface_default domain. The candidate grants only
the original implementation's camera/graphics, secure-buffer and property paths,
without the stock direct application permissions. Compiled policy confirms that
only hal_face_default and hal_miface_default may find this named HIDL service;
the new domain is not permissive. Both init scripts, Blueprint syntax, manifest
schema/merge and exact executable context matches passed host checks.

The isolated policy build reproduces the unchanged r31 binary before compiling
the candidate, with neverallow checks enabled. Existing-type permission changes
are limited to the independently reviewed thermal chown/fowner capabilities and
the face frontend finding hidl_manager_hwservice. Extended ioctl/netlink rules,
existing-type transitions and other policy statements are unchanged in the
reviewed comparisons. The baseline's existing debug/permissive domains are
reported explicitly; none is newly introduced by this candidate.

At that policy-candidate stage, complete framework VINTF compatibility and
runtime behavior had not been verified. The assembly checks below supersede
only the compatibility part of that historical status.

## Scoped r32 assembly

Complete VINTF metadata pulled from the running r31 device exposed the missing
framework matrix entry for the protected Xiaomi HIDL service. The device-owned
framework_face_matrix.xml now declares that optional service. The normal matrix
assembly command first reproduced the installed matrix byte for byte, including
its SELinux and AVB requirements; the candidate adds only the miface HAL entry.

The complete candidate VINTF check passed with all five live partition metadata
sets, actual APEX metadata, the device's 5.15.220 kernel configuration, first API
level 34 and the sheng/kalama SKUs. An earlier attempt omitted normal matrix
environment variables and failed baseline reproduction before changing product
outputs. Failed host root-directory mappings and the missing-matrix candidate
check are retained in the review rather than counted as passes.

The scoped assembly passed context type/path checks and copied only 14 reviewed
outputs into the host product staging tree. This includes the two source-built
V2 libraries, six original service files, face feature, policy/context files and
the generated system matrix. The generated global packaging contexts include
the two new executable labels. Fresh pre/post upstream audits passed for 22
public repositories with all 1243 project statuses clean.

See r32-face-assembly-build-review-20261108.json for exact hashes and limitations.
Full product and normal product module builds have not passed. No candidate was
installed on the device, no service or camera was started, and no enrollment or
authentication was attempted. Namespace behavior, startup and runtime ABI still
need device checks; working face enrollment is not yet established.

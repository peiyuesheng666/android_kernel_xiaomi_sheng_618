# piano face-enrollment reference review

The user's reference was inspected read-only on 2026-11-08. Fresh remote
queries resolve both `seventeen` and `seventeen-fw` of the main device tree
to `3f10fc25273b42d18d0bd533551a0a5c3dda0094`. The existing reference checkout
was left at its older clean revision; files were read using immutable Git
objects. No piano implementation or firmware was imported into sheng.

The relevant change is in the optional
[`android_device_xiaomi_piano-patches`](https://github.com/xiaomi-pad-8-pro-development/android_device_xiaomi_piano-patches/blob/d8aaa1ef6f31f8f0fed2dd39926fbd0357314f9c/patches/packages_apps_FaceUnlock/0001-FaceUnlock-Fit-enrollment-to-tablets.patch)
repository, commit `d8aaa1ef6f31f8f0fed2dd39926fbd0357314f9c`. It changes the
`co.aospa.sense` application in `packages/apps/FaceUnlock`, across five files:

| Change | Purpose |
| --- | --- |
| Enrollment and retry activities use `sensorLandscape` | Follow either landscape rotation on a tablet. |
| Preview bounds change from 240x320 dp to 320x320 dp | Provide bounds for either preview aspect ratio. |
| Controller reports preview dimensions after camera rotation | Supply the dimensions actually displayed. |
| SurfaceView measures itself within those bounds at that ratio | Avoid stretching the image. |

The patch does not change face recognition, the Xiaomi face HAL, gralloc,
EGL imports or secure-camera memory permissions. Its contents establish a
layout fix for that application, not successful enrollment/authentication on
the user's device or on a released piano ROM.

The optional patch runner applies changes to ROM source projects from
`vendorsetup.sh` and explicitly skips projects absent from the ROM checkout.
The reviewed `local_manifests` commit
`c262e7cddba6c797a724db45feade2cc64692906` adds the patch repository as an
optional project; it does not add `packages/apps/FaceUnlock`. Thus this fix
depends on a ROM already supplying that application. The current sheng
LineageOS checkout and its manifests contain no such project.

The main piano tree's product declarations, VINTF, extraction list and
Settings overlay contain no registration of the stock Xiaomi face service.
Its vendor tree at `c1e5a318cfe41b5c7cef74385b376fd0c2527c49` likewise has no
`mifaced`, `libmiface` or standard face-HAL payload paths in the complete,
untruncated recursive tree. The main tree retains
`ro.vendor.miface.started=true`, but a property alone does not install or
register either daemon. It also keeps
`ro.surface_flinger.protected_contents=true`; it does not demonstrate that
disabling protected composition was its face fix.

sheng currently uses its original AIDL face frontend and Xiaomi miface
implementation, with the existing Settings HAL-owned-camera preview. r38's
offscreen probe reproduces EGL_BAD_ACCESS specifically for the tested
protected camera UBWC allocation. Changing the other application's layout
cannot address that demonstrated import failure. Piano also uses the SM8750
snapalloc display stack; its allocator properties and firmware are not sheng
SM8550 inputs.

The useful idea to retain is sizing a tablet preview from its displayed
aspect ratio after rotation. It must be evaluated against sheng's actual
camera/preview transform once protected preview and enrollment callbacks are
stable. Do not copy its absolute dp dimensions, force a rotation without
checking the sensor transform, or replace the face implementation implicitly.

No runtime fix is claimed by this review. The next repair still needs to
address sheng's protected-camera composition failure and separately explain
why enrollment reports that the face is outside the frame. A global
`protected_contents=false` mitigation remains unimplemented because it would
also affect other protected GPU composition, including video; it would not
establish that face enrollment works.

Eight downloaded source blobs were checked against their Git blob SHA1s.
Exact commits, trees, SHA256s, checked scope and limits are in
`piano-face-reference-review-20261108.json`. Raw API responses and immutable
source snapshots remain outside Git in
`reports/device/r38-face-runtime-20261108`. This review changed no production
configuration, public source, SystemUI or device image and opened no camera.

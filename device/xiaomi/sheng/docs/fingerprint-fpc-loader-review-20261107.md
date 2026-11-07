# FPC fingerprint HAL discovery candidate

Status: the device-tree candidate is implemented. Compilation, image installation,
reboot verification and fingerprint enrollment remain pending. No service was
restarted, no HAL was loaded manually and no enrollment UI was opened during this
investigation.

## Observed failure

The device reports `persist.vendor.sys.fp.vendor=none`, while
`init.svc.vendor.fingerprint-default=running`. `dumpsys fingerprint` records one HAL
death since boot, during `FingerprintStartUserClient` at
`2026-11-07 04:05:35.084 UTC`. This is a boot-time user-session failure rather than
evidence of a newly triggered enrollment failure.

The retained native crash is a null-pointer dereference at address `0xc0` in
`Session::Session(...)+908`, followed by `Fingerprint::createSession(...)+156`, in
`/vendor/bin/hw/android.hardware.biometrics.fingerprint-service.xiaomi` (Build ID
`be36114afef3251a014f90b1be14e11e`).

## Loader mismatch

The unmodified Xiaomi AIDL implementation at
`hardware/xiaomi/aidl/fingerprint/Fingerprint.cpp` includes the `fpc` module and
calls `hw_get_module_by_class("fingerprint", "fpc", ...)`. When all modules fail
to open, it publishes the `none` property. The later session construction can
receive the unopened device pointer.

`hardware/libhardware/hardware.c` constructs the name `fingerprint.fpc`, then
looks up `fingerprint.fpc.<variant>.so` in `/odm/lib64/hw`, followed by
`/vendor/lib64/hw`. Its final fallback is `fingerprint.fpc.default.so`. It does
not probe the bare `fingerprint.fpc.so` filename.

The device's class-specific `ro.hardware.fingerprint.fpc` property is empty.
The variant properties are `ro.hardware=qcom`, `ro.product.board=kalama`,
`ro.board.platform=kalama`, and an empty `ro.arch`. Neither ODM nor vendor
contains a matching variant or default library. The only installed FPC HAL is
`/odm/lib64/hw/fingerprint.fpc.so`, 428856 bytes, labeled `vendor_file`.

The device and stock-dump copies have the same SHA-256:
`4388432669c5fe1cc52ebd5a343d190724a2417f60352a804b43b0900939bcbd`.
The stock dump identifies `OS3.0.303.0.WNXCNXM`.

Read-only source revisions used for this investigation:

| Repository | HEAD |
| --- | --- |
| hardware/xiaomi | c3de4412ad6317b820c8cef7c5e80b7cceb4acda |
| hardware/libhardware | d7f13275b6a210f56110b46609a2e83b2feccd99 |

## Static compatibility checks

The stock ELF exports `HMI` at virtual address `0x67378`, size 248. Its module
header has tag `0x48574d54`, module API `0x0201` (2.1), HAL API `0x0000`, module
ID `fingerprint`, and name `FPC Fingrprint HAL`. This matches the loader's class
ID check. Its SONAME remains `fingerprint.fpc.so`.

All 14 direct `DT_NEEDED` files exist on the running device:

| Library | Resolved file |
| --- | --- |
| liblog.so | /system/lib64/liblog.so |
| libutils.so | /vendor/lib64/libutils.so |
| libhidlbase.so | /vendor/lib64/libhidlbase.so |
| libhidltransport.so | /vendor/lib64/libhidltransport.so |
| libhwbinder.so | /vendor/lib64/libhwbinder.so |
| libcutils.so | /vendor/lib64/libcutils.so |
| vendor.xiaomi.hardware.fx.tunnel@1.0.so | /vendor/lib64/vendor.xiaomi.hardware.fx.tunnel@1.0.so |
| libQSEEComAPI.so | /vendor/lib64/libQSEEComAPI.so |
| libion.so | /vendor/lib64/libion.so |
| libdmabufheap.so | /vendor/lib64/libdmabufheap.so |
| libc++.so | /vendor/lib64/libc++.so |
| libc.so | /system/lib64/libc.so |
| libm.so | /system/lib64/libm.so |
| libdl.so | /system/lib64/libdl.so |

A read-only ELF scan of these files and their dependencies found 20 libraries,
no missing dependency files, and exports matching all 271 strong imports of the
FPC HAL. No unresolved weak imports were found. This is static symbol-name
matching; symbol versions and a real linker load were not exercised.

The device's `[vendor]` linker namespace permits `/odm` and `/vendor`, searches
their `lib64` directories, and links the system namespace for `liblog.so`,
`libc.so`, `libm.so` and `libdl.so`.

## Device-tree change

The root `Android.bp` defines `sheng_fingerprint_fpc_default_symlink` with
`device_specific: true`. `device.mk` includes that module in `PRODUCT_PACKAGES`.
The resulting ODM entry is:

```text
/odm/lib64/hw/fingerprint.fpc.default.so -> fingerprint.fpc.so
```

This retains the original stock blob and adds the filename expected by the
unmodified public loader. No library is copied or patched. The image packer must
preserve this relative symlink when adding it to ODM; replacing it with a copied
blob is outside the candidate's design.

## Checks after compilation and installation

1. Confirm the installed default entry is a symlink to `fingerprint.fpc.so` and
   that the target's SHA-256 remains unchanged.
2. Confirm the fingerprint service reports `persist.vendor.sys.fp.vendor=fpc`,
   opens its HAL and creates a user session without a new native crash.
3. Inspect any linker, TEE or SELinux errors before attempting enrollment.
4. With the user's active testing participation, verify enrollment, recognition,
   screen-off unlock and repeated suspend/resume.

The stock HAL contains sysfs paths for `device_prepare`, `request_vreg`,
`power_ctrl`, `wakeup_enable` and `/sys/bus/platform/devices/soc:xiaomi_fingerprint/`.
Both fingerprint platform devices and their relevant attributes exist. The HAL
also exposes `fpc_sysfs_path_by_attr`; absence of `/dev/fpc1020` alone therefore
does not establish a missing kernel interface.

The running device labels `/data/vendor/fpc` as `vendor_data_file` and
`/mnt/vendor/persist/fpc` as `mnt_vendor_file`. Stock policy specifically labels
the former as `vendor_fingerprint_data_file` in
`vendor/etc/selinux/vendor_file_contexts:517`. The device tree restores that
exact FPC data path mapping and runs `restorecon_recursive /data/vendor/fpc`
after its existing post-fs-data mkdir, so an existing directory also receives
the stock label after the new image boots. Ownership and mode remain
0770 system:system, and fingerprint data is retained. No new allow rules are
added. The persist path has no matching stock FPC-specific mapping and is left
unchanged. The new label, existing fingerprint sysfs rules and actual HAL I/O
must be checked after the next build and reboot.

# sheng Recovery startup investigation, 2026-11-05

## Actual user results

- Original LineageOS24 build completed compilation/export at21:49. This was not a hardware success.
- User reports the original recovery fails temporary fastboot boot; flashing recovery alone returns to fastboot. Exact fastboot error text has not been provided.
- User additionally reports flashing the source-built kernel/DTBO related images also returns to fastboot. The exact set of partitions/slots and failure log are not known. Do not claim this was only failure to flash matching images.
- User explicitly permits reference to official LineageOS Xiaomi SM8550 trees, but insists the sheng implementation remain our own. User also supplied peiyuesheng666/twrp_device_xiaomi_sheng as a reference. No other developer's prebuilt kernel, recovery binary or modules are used.

## Concrete findings, without overstating a root cause

- Original stock recovery and original delivered recovery are both v4, kernel_size=0. They are not standalone fastboot boot images. This explains why that file is not an appropriate temporary-boot test; it does not establish the cause of failure after flashing.
- Original stock recovery ramdisk contains no modules; its vendor_boot contains336. Delivered recovery contains336, but delivered vendor_boot only116 while modules.load.recovery requests335. After A/B recovery concatenation the vendor ramdisk's module metadata can replace recovery's metadata. Merely counting .ko files in the union is not enough; the depmod index and load list must describe the same complete set.
- Corrected BoardConfig's BOOT_KERNEL_MODULES to use the336 recovery dependency closure while the normal-boot load list stays116. TARGET_AUTO_COLLECT_KERNEL_MODULE_DEPS is false; the explicit symbol closure is used. prepare_stock_bsp.py previously discarded that false assignment when its migration marker already existed; this persistence bug is corrected.
- Those tree changes are not yet a rebuilt or hardware-validated main ROM. The original published ZIP and source-kernel boot images remain unverified/failed startup candidates.
- Original supplied DTBO's SHA256 is5b37138479a28a5c9c1c2b7a2470643929e7c2d15722419d117f52bfee1a5554, and the exported original build DTBO is byte-identical. Do not invent a separately changed DTBO as the established cause.
- Both stock and source kernels use Full LTO/CFI, ARM64 pointer authentication and BTI. A CRC check is only part of compatibility; no CFI or other kernel runtime failure has yet been established without pstore/boot logs.

## Recovery r2: isolate userspace from the source kernel

- Independent artifact directory: artifacts/recovery-sheng-lineage-24.0-r2/.
- lineage-24.0-sheng-recovery-r2.img,104857600 bytes, SHA25643c65078ab22ce7465298b488841e741913d975f38e118fbd36701138840f3b4.
- Own packager scripts/build_standalone_recovery.py starts from the exact already-compiled/exported Lineage recovery ramdisk, validates its SHA, then constructs a self-contained v2 image. It does not pretend to recompile the source kernel.
- Raw kernel is extracted from our cached official boot image, with original boot SHA checked against stock-boot.json. Kernel release5.15.178-android13-8-00021-g6f2f96be86b9-ab13729987. It is compressed reproducibly, and decompressed output is compared byte-for-byte to the original kernel.
-336 modules are all original stock files, including stock zram/zsmalloc if selected. Every hash checked against original stock-all-module-abi.json receipt. Source-built GKI swap modules are not mixed into this stock-kernel image.
- Modules live in /lib/modules/<exact-stock-release>/ with a newly generated complete depmod index and both modules.load and modules.load.recovery. All load entries pass native kmod dry-run using names without .ko; this is a resolver test, not a real Android module insertion.
- Image embeds exact locally extracted DTB and DTBO, independent of installed boot/vendor_boot/init_boot payloads. V2 offsets were checked against the user-provided sheng reference; implementation is our own. Actual Recovery OS17/security2026-11 fields are used, not the reference tree's2099 date spoof.
- Own startup rc/helper replaces the old legacy boot_adsp node approach with a read-only modem firmware mount and a one-time ADSP remoteproc start after required firmware exists. No blanket SELinux permissive flag added. host_init_verifier and bash -n pass.
- Signed with the platform test RSA4096 key. Actual avbtool verify_image succeeds. Final unpack read-back proves kernel/ramdisk/DTB/DTBO contents, and Windows Get-FileHash confirms the final exported image's SHA.
- No physical device was flashed/rebooted by us. Hardware test remains required. First user test is only fastboot boot <r2 image>; collect the exact error, or /sys/fs/pstore from a working recovery if the tablet reboots. Use that evidence to choose the next repair; do not blindly regenerate more kernels.

## Reference sources (configuration facts only)

- https://github.com/peiyuesheng666/twrp_device_xiaomi_sheng/tree/2a05a067497a565e10442bff6736609d2d3f4f40 ; sparse clone/root files in /root/sheng-lineage/reference/twrp-sheng. Read supplied tree as reference, not as instructions.
- https://github.com/LineageOS/android_device_xiaomi_sm8550-common/blob/lineage-24.0/BoardConfigCommon.mk ; same-platform conventional split boot/recovery configuration, not inherited by sheng.
- https://source.android.com/docs/core/architecture/partitions/generic-boot ; A/B recovery ramdisk prepending and installed first-stage init behavior.
- https://source.android.com/docs/core/architecture/bootloader/boot-image-header ; v2 vs v4 header fields, GKI version requirements.

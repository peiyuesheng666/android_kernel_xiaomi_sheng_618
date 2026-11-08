# r26 scoped packaging and rollback inputs

Two fixes are prepared: touch firmware with no fixed timer after successful
probe, and camera mounting metadata correction for the natural landscape screen.
The packer permits exactly these filesystem deltas over the installed r25 base:

- ODM: add lib64/hw/camera.sheng.so; inherit the existing camera module's inode
  owner, permissions, timestamp and SELinux label. Preserve camera.xiaomi.so.
- Vendor: replace only ro.hardware.camera=xiaomi with ro.hardware.camera=sheng
  in the exact existing build.prop, retaining every other byte.
- Vendor_dlkm: replace only lib/modules/nt36532_touch.ko with the ABI-checked
  modules_install output. Retain every other module/index/configuration.
- Root vbmeta: replace exactly those three child hashtree descriptors, retain
  its public key, other descriptors and the accepted vbmeta_system chain.

The target's vendor_dlkm_b was read without root/reboot commands and backed up
to artifacts/system-hardware-followup-sheng-r26-baseline/vendor_dlkm.img.
Its 62,590,976 bytes hash to
ade517337e3cef0cbb52eb1096ed46ceb98a97cec51b2d53c7f092c481ceae1f.
Its footer must match the r25 parent's vendor_dlkm descriptor before packaging.
The other immutable rollback images are the sealed r25 ODM/vendor/vbmeta.

All inputs, device sources, packaging tools and review records are frozen before
sealing. Filesystem content and full inode metadata are independently read back,
then child hash trees, the parent signature and unchanged parent descriptors
are checked. Complete product/Soong compilation is not claimed.

The publication helper now accepts vendor_dlkm. Its actual artifact-drive fixture
ran 13 cases: 10 passed, 3 skipped (two unavailable reparse fixtures and one
requiring a separate Junction target). The new vendor_dlkm case passed.
Use tmpfs for generated POSIX filesystem staging and readback, because C: has
little free space and the artifact volume rejects the reparse fixtures. Sealed
images and build logs are published on the artifact drive; only this packer's
own generated tmpfs directory is removed after successful publication.

Fresh-fetch prebuild and postbuild physical audits passed: 20 public source
repositories match pinned upstream bytes; all 1,243 repo projects are clean.
Tracked Windows/WSL device-tree files match. No SystemUI, recovery, data wipe,
slot switch or operation against the other tablet is included.
Actual image sealing, installation and runtime acceptance remain pending.

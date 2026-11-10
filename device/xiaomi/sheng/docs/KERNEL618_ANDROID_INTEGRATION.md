# Android device-tree integration of the sheng 6.18 kernel

The user selected the tested 6.18.32 sheng kernel for future device-tree builds
on 2026-11-10. The Android target should distribute loadable modules through
the normal boot and DLKM partitions, instead of embedding the complete module
archive in Image as the current r70 HyperOS package does.

- `boot`: the 6.18 kernel Image and its built-in drivers.
- `vendor_boot`: the dependency closure of modules needed by first-stage init,
  plus the separately reviewed recovery module closure where applicable.
- `vendor_dlkm`: the remaining vendor, SoC and tablet modules built for 6.18.
- `system_dlkm`: the selected generic kernel modules built in the same build.

The module partition lists must be derived from the actual 6.18 outputs and
dependencies. The current 5.15 stock loading lists and module binaries cannot
be reused as a compatible 6.18 package. Module ABI, symbol versions, signatures,
dependency ordering, firmware paths and production SELinux domains need checks.
No vermagic or CRC rewriting is permitted.

The existing project already retains an unembedded `kernel-Image` after
`buildkernel.sh`, with a separate module build stage. Use these matching
outputs as inputs to a new Android staging step; do not extract a kernel and
combine it with old DLKM partitions. Keep the current r70 embedded release
recoverable while bringing up first-stage loading, recovery and Android.

Update the device-owned build configuration only after these partition inputs
exist and their boot chains have been reviewed. Validate Android services,
graphics, charging, suspend/resume, touch and peripherals on the complete new
set. HyperOS r70 acceptance does not establish compatibility with this
LineageOS vendor/userspace build.

For the 2026-11-10 restoration, r38 retains its previously tested 5.15 image
set as a control. The requested 6.18 partition-based integration is planned,
not yet built or installed. Public repositories remain at manifest revisions;
Android adapters and packaging changes belong to this device tree.

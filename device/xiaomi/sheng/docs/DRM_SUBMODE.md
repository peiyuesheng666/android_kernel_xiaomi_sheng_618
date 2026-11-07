# sheng DRM submode compatibility

The 144 Hz diagnostic exposed all four native modes but failed composition.
Resource debug reported 546.030 MHz required versus the stock 514 MHz limit.
The panel remained at the previously committed timing. Power-off then failed
resource reconfiguration, preventing normal wake; reverting required an r5 reboot.
This candidate was not packaged or declared passing.

Stock `libsdmdal.so`'s `HWDeviceDRM::PopulateDisplayAttributes` uses a 48-byte
`DRMSubModeInfo` stride and loads the pixel clock at offset 40. It stores that
value in `HWDisplayAttributes::clock_khz`. The manifest CAF header omits this
field (40-byte stride) and CAF DAL uses `drmModeModeInfo::clock` instead.
Stock sheng has a burst video panel with separate timing and submode clocks.
Both ABI and clock selection must match the unchanged stock `libsdedrm.so`.

`display/dal` retains the CAF sources and notices at the revision recorded in
`SOURCE_BASELINES.json`. Only the local DRM header and pixel clock assignment
are adapted. A static assertion requires the stock LP64 size. Missing stock
clock data returns an error instead of bypassing resource limits. Public CAF
sources remain unchanged. The preferred device-compiled `libsdmdal` follows
the same source/prebuilt selection pattern as device PAL; normal product
builds install it without a patch runner.

Runtime testing is pending. Composer's native-mode gate remains opt-in until
native timings, switching, sleep/wake, and reboot have been verified.
The refresh packager uses verified r5 as its base, changes composer and DAL
only, and preserves r5 audio, sensors, inode metadata, and other AVB descriptors.

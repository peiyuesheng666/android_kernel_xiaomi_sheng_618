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
Both the producer and consumer must carry the stock pixel clock field.

`display/dal` retains the CAF sources and notices at the revision recorded in
`SOURCE_BASELINES.json`. Only the local DRM header and pixel clock assignment
are adapted. Device-owned `display/sde-drm` also retains the CAF sources and
public DRM API, adding parsing of the kernel's `pixel_clk_khz=` mode property.
Exact submode-prefix matching prevents `preferred_submode_idx=` from creating
a spurious submode. A static assertion requires the stock LP64 size. Missing stock
clock data returns an error instead of bypassing resource limits. Public CAF
sources remain unchanged. The preferred device-compiled `libsdmdal` follows
and `libsdedrm` follow the same source/prebuilt selection pattern as device PAL; normal product
builds install it without a patch runner.

Runtime testing is pending. Composer's native-mode gate remains opt-in until
native timings, switching, sleep/wake, and reboot have been verified.
The refresh packager uses verified r5 as its base, changes composer, DAL, and DRM
only, and preserves r5 audio, sensors, inode metadata, and other AVB descriptors.

The 2026-11-07 focused build exposed an unqualified `move()` rejected by the
current C++ compiler and a `libsdedrm` Make alias that is not exported after
preferred-prebuilt selection. The device snapshot now uses `std::move`, and
the hardware helper requests the two installed library paths. The composer,
DAL, and DRM outputs compiled successfully through the generated normal Ninja
graph; the preferred device ELF inputs and installed outputs were verified.
The postbuild fresh-fetch audit is `upstream-refresh-submode-build-audit.json`:
all 1,243 repo-managed projects are clean and all 13 public-source checks pass.
This is build validation; 144 Hz runtime validation is still pending.

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

Composer's native-mode gate originally remained opt-in during diagnostics.
With the corrected stock clock ABI, it now defaults on for native-resolution
60/90/120/144 Hz; the property still allows disabling it for rollback.
Native switching and 144 Hz sleep/wake passed kernel/HWC checks. The user
confirmed normal output/touch before flashing and after the r6 reboot,
including a physical power-button sleep/wake test at real 144 Hz.
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

DSI mode data is validated in `HWDeviceDRM::Init` before the legacy void
`InitializeConfigs` path. Bounds are checked before topology access, and stock
submode clocks are required only for DSI; DP and virtual displays retain their
standard timing clock. No class layout or virtual-function signatures changed.
The corrected DAL rebuilt successfully and was loaded at native 60 Hz; the
kernel reports an active CRTC and normal device composition after wake.

`scripts/ShengDrmModeProbe.c` queries only DRM resource, connector, property,
and property-blob ioctls, using a read-only descriptor. It does not acquire
DRM master, set modes, access framebuffer pixels, or capture images. Its static
ARM64 build passed `-Wall -Wextra -Werror`. The live mode-properties blob
contains nonzero stock submode clocks for all seven native timings:

| Rate (Hz) | Submode clock (kHz) | DRM timing clock (kHz) |
| --- | --- | --- |
| 120 | 396694 | 932655 |
| 144 | 396906 | 1040058 |
| 90 | 396826 | 798797 |
| 60 | 396694 | 932655 |
| 50 | 396826 | 798716 |
| 48 | 396826 | 798748 |
| 30 | 396826 | 798797 |

Raw output is stored locally in
`reports/device/native-refresh-kernel-mode-properties.txt`; it is not an image.

The temporary build reached real native 60, 90, 120, and 144 Hz, verified in
DRM CRTC state and SurfaceFlinger. At 144 Hz, the display entered inactive
state on sleep and became active again at the same timing on wake, with device
composition and no observed resource-limit errors. A separate idle period
ended in `mLastSleepReason=timeout` at the user's current 15-second timeout.
Visual output and touch still require user confirmation.

Revision r6 changes only the composer and the two compatible display libraries
over r5. Its preferred inputs, image signatures, EROFS file readback, every
vendor inode's metadata, and unchanged non-vendor AVB descriptors passed.
The r6 delta was flashed to slot b and boot-verified on 2026-11-07. The installed
vendor hash and the first 8192 bytes of vbmeta match the packaged images;
vbmeta's physical partition is larger than the image. There are no temporary
vendor file binds after reboot, and the stock-clock libraries match compiled
device-owned outputs. The peak is set to 144 Hz with a 60 Hz lower bound.

The initial report of a second-screen stall occurred while framework startup
was completing: AMS became ready at 51938 ms and enabled the screen at 52328 ms.
FallbackHome logged that the user was not unlocked. Boot completion and stopped
bootanimation were subsequently confirmed, and the user reported a normal
lockscreen/desktop. The known fingerprint HAL crash and general startup latency
remain separate followups; this display delta does not claim to fix them.

# sheng speaker paths

The tablet's six amplifiers use the stock four-channel, 48 kHz, 24-bit TDM
backend. Six physical speakers do not imply six PCM channels. The stock slot
map is `2/2/0/3/3/1`. Plain stereo expands to logical FL/FR/LB/RB at
unity gain. The separate speaker mixer maps those four logical channels to
physical slots for the current display angle.

`audio/pal` contains the device-owned `libar-pal-sheng` source module. It installs
with the original `libar-pal.so` name through a preferred prebuilt whose input
is that freshly compiled source module. This disables the public source's
installation rule and replaces its link dependencies before Make packaging.
The public PAL repository remains at its unmodified upstream revision. Matching
GSL API headers live in `audio/gsl` and are attached during vendor extraction.
The kernel's normal UAPI export uses `interfaces/kernel/uapi`, a header-only BSP snapshot;
only the Cirrus kernel-private declarations are guarded from userspace. Header
export and C90 checks remain enabled.

Previously tested device behavior includes six-speaker PCM, mono/stereo MP3
and AAC offload, left/right channel isolation, volume, pause/resume and reboot.
Rebuilding these fixes as device-owned modules is a separate validation step.
The device-owned migration modules compiled successfully and the validated
images were flashed to slot b on 2026-11-06. The r4 startup followup passed
boot on 2026-11-07; the user confirmed six speakers at normal volume and the
installed PAL hash matched the compiled device module. Live Dolby control
remains under investigation; audibility of that effect is a separate check.

## Four-angle speaker rotation candidate (2026-11-07)

The phone HAL collapses three display angles into one speaker state, and its
PAL skips quad rotation. `audio/rotation`, selected by
`ro.hardware.audio.primary=sheng`, delegates to the unchanged upstream
`audio.primary.kalama` and forwards all four display angles to device-owned
PAL. Device-only enum values 0x100..0x103 retain the original LR/RL ABI.

The factory path has an MFC tagged `TAG_MFC_SPEAKER_SWAP` (MIID 0x4174),
additional processing, then a final MFC (MIID 0x4474). The final MFC is exposed
under stock tag 0xc000003d, despite that tag's generic MSIIR name. Its module
ID is 0x07001015 and its normal output IDs are 1/2/4/5. Reordering 0x4174
alone left audible placement fixed. Reordering 0x4474 to [5,2,4,1] produced
low-left/high-right with the USB port on the right and display rotation 0.
The user confirmed that bounded live test on 2026-11-07.

The candidate now applies the four unique output IDs at the final MFC for
active rotations, new speaker streams and route reconnections. The earlier
MFC retains its normal format. Dolby keeps stereo source input and native
quad output; the rotation stage permutes four distinct channels at unity gain.
Other devices retain the upstream stereo-swap behavior. The first automatic
test passed both landscape postures, while both portrait postures reversed
left/right. The portrait entries were exchanged based on that physical test.
The revised entries passed all four physical poses with Dolby both disabled
and enabled; the user confirmed all six speakers. Real music and AAC offload
retained immediate switch/mode/EQ control. Mono MP3 and stereo AAC both used
compressed offload and completed after the scripted two-second pause/resume.
The validated PAL SHA-256 is
`cbb24166fde6042d1bdfb60a3ae362aa5d0f8559390bff0ac61bd8364c998e1e`.
Revision 5 was packaged, flashed to slot b and rebooted successfully. The
installed PAL hash matches the validated build, `audio.primary.sheng` is loaded
from vendor, SELinux is enforcing and no temporary bind mounts remain. The
user confirmed normal display, six speakers, immediate Dolby controls and
correct left/right placement at all four poses after reboot.

`ShengSpeakerFormatProbe.c` can target the earlier or final stock MFC.
`ShengSpeakerMatrixProbe.c` tests coefficient tables without changing saved
Dolby settings. Those matrix experiments did not change audible placement
and are not used by the production candidate. The channel playback probe
accepts `on|off` and 1..8 rounds and does not alter saved mode or EQ.

The preceding complete hardware build and fresh-fetch public source audit
passed for 13 audited repositories and 1,243 clean manifest projects. The
installed permanent image is now r5. The final rotation and native Dolby
changes are included in that verified image.

`scripts/package_sheng_dolby_followup.py` prepares an optional r5-or-later
development image over the exact installed r4 vendor/AVB and r2 ODM/system_ext
bases, preserving the r4 display-startup fix. It includes the compiled PAL,
rotation adapter, Dolby clients, effect configuration, app and required
hardware properties. It verifies base hashes, preferred PAL input, APK signer,
partition sizes, image contents, existing EROFS metadata, installed public
policy input IDs, signatures and unrelated AVB descriptors. Syntax and base
hash checks, image readback, signatures and reboot validation passed for r5.
Ordinary rebuilds use the device's product modules and need no delta packager.

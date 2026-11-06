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
The kernel's normal UAPI export uses `kernel/uapi`, a header-only BSP snapshot;
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

The user identified fixed portrait channel placement when the display was in
landscape. The upstream phone HAL collapses 0/90/180 into LR and only sends
RL for 270; upstream PAL skips rotation for devices with four channels.
`audio/rotation` adds a small primary HAL adapter selected by
`ro.hardware.audio.primary=sheng`. It delegates all audio callbacks to the
unchanged compiled `audio.primary.kalama` and forwards the complete display
angle to the device-owned PAL instead of the phone's two-state request.
Other parameter keys still reach the original HAL.

The post-DAP mixer receives a four-by-four Q14 permutation for every angle.
The permutation preserves each native Dolby channel and unity gain; it does
not reduce Dolby to stereo or copy channels after it. Plain PCM and compressed
paths use the same logical quad order. Rotation is applied to active streams,
new streams, route reconnections and pause/resume. Existing LR/RL enum values
are retained, with device-only values 0x100..0x103 added for the four angles.

The host impulse-routing check passes for four angles. The candidate's full
build and physical channel/dynamic rotation checks are pending. The preceding
clean native-quad batch compiled successfully in 266 tasks, with fresh-fetch
upstream verification passing for all 13 audited public repositories and clean
status across 1,243 manifest projects. The installed image is still r4.

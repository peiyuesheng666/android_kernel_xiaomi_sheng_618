# sheng speaker paths

The tablet's six amplifiers use the stock four-channel, 48 kHz, 24-bit TDM
backend. Six physical speakers do not imply six PCM channels. The stock slot
map is `2/2/0/3/3/1`. Stereo-to-quad Q14 coefficients are
`[0x4000,0,0x4000,0,0,0x4000,0,0x4000]`.

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
images were flashed to slot b on 2026-11-06. Boot and hardware regression
checks remain pending while ADB is unavailable after reboot.

# sheng Dolby integration

`compat/dolby` supplies the two stock arm64 Dolby clients and a private
foundation ABI. Its foundation-defined Android symbols use a private namespace
so the old AHandler layout does not conflict with unrelated platform clients.
The DAP coefficient handling uses the verified four-channel, 128-byte bound;
FORTIFY remains enabled. The exact regenerated blob hashes and provenance are
recorded by `scripts/build_sheng_dolby_foundation_compat.py`.

The device extraction hook points the generated arm64 client modules at
device-owned filegroups and their private foundation dependency. They retain
the original filenames and have only one installation rule. The generated
stock client blob files and public framework foundation stay unchanged.
The new foundation gets an exact `vendor_file` context; graphics HAL
labels retain their existing `same_process_hal_file` contexts.

`dolby/ShengDolby` provides a Settings/Sound entry, tablet layout, mode selection
(including the Chinese label “人声”), tone/dialog controls and five grouped EQ
sliders backed by the native 20 bands. The user's saved EQ settings are retained.
Temporary validation confirmed six speakers and a changed sound when enabled.
The rebuilt-image Settings, playback and Dolby regression tests are pending.

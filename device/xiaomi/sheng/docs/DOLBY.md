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
The r4 image boots normally; the user verified the Settings entry and six
speakers. However, toggles, modes and EQ had no audible effect. DMS accepted
the profile, but the native driver logged failed realtime DAP updates and
PAL returned -EINVAL. Device-owned PAL tracing is being used to compare the
requested and active stream routes.

The trace showed stock DMS trying stream IDs 18/3/2 for the speaker DAP tag
0xC00000DB, missing generic (8) and low-latency (1) playback. The device PAL now
routes the final deep-buffer DAP request to compatible speaker media streams,
with payload bounds checks and success only when a DSP write succeeds. Other
devices, tags, raw/call/record/haptics streams retain their original matching.

EQ and dialog-strength sliders now send changes while dragging. Per-profile
parameter generations discard superseded writes/readbacks, so rapid gestures
do not falsely report a mismatch against a newer value. Saved custom values
and the stock processing profiles are retained. Live A/B testing is pending.

DSP readback diagnostics distinguish DMS's stored values from the actual
active module. The PAL query copies only the returned data length, excluding
the parameter ID, to avoid the original four-byte overread/overwrite.
Enable values 0 and 1 were read back from the DSP correctly. The user still
reported no audible change. Bundle parameter ID zero is not queryable: the
trace now checks its individual APM records, validates the DSP response header
and error code, and uses the matching allocation/deallocation operation.
Active GEBS, GEON, IEON, DEON and enable values have been read back correctly;
the user still reported no audible effect while changing EQ during playback.
A successful control write is not an audibility claim.

`scripts/ShengAgmDapProbe.c` makes read-only queries of a selected live graph.
It uses SPF's actual header order (module, parameter, size, error), bounds the
tag list and responses, and can query either DAP or an explicitly selected MFC.
The deep-buffer speaker graph has DAP module 0x100108db; both PSPD and device
PP MFCs currently output four channels, whereas DMS reports a stereo stream.
A temporary experiment fed DAP stereo and moved quad expansion to the device
PP MFC. DSP format queries confirmed the change, but the user still heard no
live effect while all speakers worked. The experiment was reverted; it is
not part of the product configuration.

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
A temporary experiment made PSPD stereo and kept the device PP MFC quad.
The user still heard no live effect while all speakers worked. Inspecting
the actual stock topology later showed that both converters precede DAP,
so that experiment did not establish stereo input to DAP. It was reverted.

The stock media volume listener has EFFECT_FLAG_NO_PROCESS, which the upstream
AudioFlinger supports. It is restored in the music postprocess chain to feed
playback activity and volume to PregainSynchronizer without touching PCM.
The arm64 pregain handler has the same old AHandler layout as DAP (its looper
pointer is at offset 96). Both pregain and listener now use the device-private
foundation; their stock dumps and public foundation stay unchanged. The
listener was created, enabled and received media volume on the live track.
The user still heard no effect while all six speakers worked.

Temporary XML binds must use `vendor_configs_file`, matching the original
file. Labeling them `vendor_file` prevents AudioPolicyEffects from reading
the music chain, even when the vendor effects service can load its libraries.

`ShengAcdbGraphProbe.c` queries the original calibration in an independent
process, using only GET commands. The stock topology is serial:
PSPD MFC 0x40b6 -> mixer -> device PP MFC 0x401d -> DAP 0x4615 ->
speaker processing -> speaker-swap MFC 0x4174 -> hardware endpoint.
Build it with `SHENG_PROBE_SOURCE=ShengAcdbGraphProbe.c` and
`SHENG_PROBE_OUTPUT=sheng-acdb-graph-probe` using the AGM probe build script.
This confirms connections in calibration, not actual processing audibility.

The default-off diagnostic `vendor.audio.sheng.dap_stereo_stage` explicitly
sets both pre-DAP converters to stereo and the post-processing speaker-swap
converter to quad with the verified physical speaker mapping. It is limited
to sheng stereo PCM on the speaker TDM backend. DSP format readback and
live audibility validation are required before adopting this configuration.

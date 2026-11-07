# LHDC v5 read-only investigation

2026-11-07, while r19 AON/Health was building. No Bluetooth toggles,
playback, pairing or codec changes were made.

The installed Bluetooth aconfig flags a2dp_lhdc_api and lhdc_codec_support
are enabled. LHDCV5 is present in dumpsys Bluetooth codec configuration.
The pinned stack links liblhdcv5_encoder statically; absence of a separate
liblhdcv5BT_enc.so is not evidence of a missing encoder. The stock vendor
lib_bt_lhdc.so is installed and is a distinct DSP/offload component.

A2DP offload is enabled. a2dp_offload_user_codec_selection is disabled and
read-only. In bta_av_co.cc, the explicit user priority branch is gated by
this flag; otherwise a vendor hardware codec may win over software LHDCv5.
This is a candidate explanation when a peer advertises competing hardware
codecs, not a proven cause for this user's headset. Actual peer selectable
capabilities, requested codec and chosen output must be collected during
user-controlled testing before changing anything.

The effective persist.vendor.qcom.bluetooth.a2dp_offload_cap does not include
LHDC, while the device's other persist.vendor.bt.a2dp_offload_cap line does.
Do not declare DSP LHDCv5 support or disable all hardware offload from a
property string alone. Public Bluetooth source remains unchanged.

Evidence: workspace reports/device/r19-runtime/lhdc-read-only-inventory.txt,
lhdc-loader-baseline.txt, lhdc-runtime-flag.txt and lhdc-selection-readback.txt.

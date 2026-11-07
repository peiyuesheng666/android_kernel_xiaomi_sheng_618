# r18: preserve visible order and exchange color functions

Final user request: keep 自适应 / 生动 / 鲜艳 in that order and exchange the
last two functions. The r17 Settings name/value table did not control order:
ColorModeUtils.getAvailableColorModes reads Framework config_availableColorModes;
both ColorModePreferenceFragment and ColorModeScreen iterate that list. The
r17 Framework list remained 0,1,2, so its visible labels/functions did not change.

r18 changes the Framework list to 0,2,1 and maps Settings labels to 0 Adaptive,
2 Vivid/生动, 1 Saturated/鲜艳. This preserves the visible names and order while
生动 now selects the original framework Saturated behavior (2), and 鲜艳 now
selects the original framework Boosted behavior (1). Framework mode semantics,
composition mappings, saved numeric mode, neutral/adaptive mode 0 and white
balance parameters are unchanged. Night Light/white-balance restrictions follow
the actual selected framework mode. No vendor render intent or GPU fallback.

The two device-owned RROs built in 01:35. Fresh pre/post fetch audits passed
13 fixed public repositories and all 1,243 projects. Compiled resource dumps
confirm both lists 0,2,1 and Settings names Original/Vivid/Saturated. Combining
both arrays with Chinese strings yields exactly [(自适应,0),(生动,2),(鲜艳,1)].
Independent r18 packaging/flash tools pin the installed r17 chain, both new
APK hashes and strict metadata/AVB checks. Only the two ODM APKs plus vbmeta
will be replaced. Python compile and PowerShell parsing passed. Existing r17
inputs and outputs are immutable; publication/runtime are recorded separately.

The user's r17 physical tests accepted no wake/password yellow flash, smooth
Night Light transition, normal picture/touch and working lift-to-wake. These
remain the accepted baseline; the forced-warm PCC trial's small reversals are
still documented and do not establish all-condition strict monotonicity.
AON inventory found the existing unavailable Screen attention entry; no camera
or attention detection was started. Input candidates remain paused.

## Compiled resource comparison

The retained r17 Framework APK was dumped from its verified packaging tree and
compared with r18's compiled Framework APK. Their complete aapt2 resource dumps
are identical after substituting the single config_availableColorModes array
0,1,2 -> 0,2,1. In particular, every white-balance resource, transition duration,
nominal XYZ and composition-color mapping is unchanged. The r18 source-combined
menu is 自适应=0, 生动=2, 鲜艳=1; standard Settings selection writes those exact
numeric IDs. Before r18 flash, the user's saved mode is 0, Night Light is 0,
and display_white_balance_enabled remains absent/default true.
Evidence: workspace logs/r17-retained-framework-resources.txt,
logs/r18-framework-resources.txt, logs/r18-settings-resources.txt, and
reports/device/r18-runtime/before-flash-settings.txt.

## Exclusive r18 publication

Full filesystem readback confirms the changed-file set is exactly the two ODM
RROs. Permission/SELinux/UUID, APK certificates, unchanged baseline chain hashes,
and AVB parent descriptor/key checks passed. The ODM hashtree descriptor is the
only parent vbmeta descriptor change. Images were published to an exclusive r18
directory without replacing prior versions. Frozen spec SHA256 is
 e20d765c2b4b6f44388155ec8071a0d1e8204bb93f07d2329104ab84538e10ab.
Image hashes and scope evidence are in packaging-r18-20261107.json.
Runtime acceptance is separate and pending at publication.

## Installed r18 verification

ODM and vbmeta were flashed on b and rebooted, with no erase or slot change.
Initial reads occurred during boot; the later boot-ready check gives root=0,
boot-completed=1 and boot animation stopped. All six exact installed chain hashes
and the two new RRO, unchanged sensor and accepted color-core hashes match.
Live Framework available modes are 0,2,1; live Settings strings are 自适应,
生动,鲜艳 and their values are 0,2,1. Thus the actual generated menu keeps its
visible order and associates 生动 with original mode2, 鲜艳 with original mode1.
White-balance default remains enabled via the absent saved key, its increase
transition remains 3000 ms, and Night Light remains the user's saved off state.
SurfaceFlinger reports device composition and usesClientComposition=false.
A final physical menu/function check is pending; prior accepted yellow-flash
and Night Light fixes remain the baseline. Evidence: runtime-r18-20261107.json
and workspace reports/device/r18-runtime.

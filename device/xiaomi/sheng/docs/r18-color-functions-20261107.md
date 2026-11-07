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

# r17 color labels and r16 follow-up

Settings options are now 自适应 / 鲜艳 / 生动 (Adaptive / Saturated / Vivid),
with corresponding framework IDs 0 / 2 / 1. Labels and values move together;
saved mode numbers and each mode's behavior are preserved. Adaptive is a color
mode name; 显示屏白平衡 remains the existing independent ambient-color switch.
No additional white-balance switch is added.

The Settings RRO built in 01:32. Fresh before/after fetch audits passed for
13 fixed public-source revisions and all 1,243 project statuses. APK resource
readback confirms Adaptive/自适应 and the 0,2,1 order. The new independent r17
tools pin all six r16-chain images and this compiled Settings APK. Only ODM's
Settings RRO and the associated vbmeta parent are outputs. r16 and earlier
frozen specifications/images remain unchanged. Python compilation and
PowerShell parsing passed; existing strict filesystem and AVB helpers are reused.
Publication and runtime acceptance are recorded separately after completion.

r16 has booted with six exact installed hashes and the corrected Framework RRO
and front-CCT sensor service. A focused probe received positive front-CCT values
5828..9199 K without the invalid startup zeros. Override-baseline trials which
required an exactly settled 5300 K timed out; these do not prove regression
failure. A subsequent actual-warm baseline trial at 5840 K captured 35 hardware
PCC samples. The old large abrupt ~1-second jump was absent, but small early
and late reverse changes remain in this forced overlap test (largest adjacent
G/R increase 0.001770 and B/R increase 0.004547). This is not full smoothness
acceptance; await the user after a fresh reboot with natural ambient input.
The diagnostic restores its setting keys, timeout and CCT override.

The user confirmed 抬起亮屏 works on 2026-11-07 and requested no further work
on it. Standard wake-up one-shot pickup type25 is subscribed by SystemUI. The
existing standard menu is under System / Gestures and also Lock screen. No
pickup code or settings change is made. AON inspection found the existing
屏幕感知 switch in Screen timeout, but config_adaptive_sleep_available=false,
no default attention service and no installed Xiaomi AON APK; availability
requires later integration. No camera or attention detection was started.

## Exclusive r17 publication

The new r17 batch passed full readback, file permission/SELinux/UUID checks,
APK certificate verification and AVB descriptor/key verification. The changed
file set is exactly overlay/SettingsResOverlaySheng.apk in ODM. The single ODM
hashtree descriptor is the only vbmeta descriptor change. Vendor and the other
four chain images remain their verified r16 baselines. The frozen spec digest
is 24126bade96752a2854e6672a5c6a9d54fa30ec9bedf60ddb37e5b2db57e4867.
Published hashes are in packaging-r17-20261107.json. Existing r16 output/spec
are unchanged. Runtime/user acceptance remain separate.

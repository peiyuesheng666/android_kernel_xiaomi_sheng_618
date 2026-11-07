# r16 ambient-white-balance candidate

The two r15 regressions disappeared when the existing 显示屏白平衡 switch was
temporarily disabled. Preserve that containment until this candidate is tested.
No additional settings switch or public-framework modification is introduced.

The device sensor bridge rejects only nonpositive/nonfinite front-CCT samples.
This prevents the observed 0 K startup samples from entering Android's ambient
filter, low-light blend and output clamp. Other sensors, positive Kelvin data,
flush and additional-information events are preserved. ASan/UBSan coverage
passed; there is no assumed clamp based on the incorrect sensor maxRange.

The resource nominal-white XYZ now uses the actual framework's cctToXyz(6500):
(0.968583405,1,1.12105489). This is an algorithmic neutral reference, not a new
panel measurement. Native-primary fallback and its white remain the verified
sRGB/D65 values. Anchoring adaptation at the same XYZ as the disabled nominal
CCT ensures the transform meets identity continuously, so the last DWB step
does not replace a remaining 3.07-percent XYZ component with identity.
The pure on-device color-math probe confirms exact identity at 6500 K and its
immediate neighboring CCT values using the unchanged framework implementation.

DWB's increasing-CCT fade changes from 1000 to 3000 ms, matching Night Light's
activation transition. The upstream gradual 40000-ms ambient-warming duration
is retained. This removes the early completion of the DWB exit halfway through
Night Light's fade; actual smoothness still requires hardware and user testing.
Original 5300-8100 K limits and 5600 K low-light target remain unchanged.

The intended batch contains only the Framework RRO and the device-owned sensor
service, plus the corresponding vbmeta parent, over verified r15. The working
color-core library and Settings RRO remain at their accepted r15 versions.
Build/publication/physical acceptance are separate milestones, recorded after
they complete. Pure math does not establish hardware acceptance.

## Build and packaging checks

The sensor service and Framework RRO compiled successfully in 01:45. Installed
APK resources contain the matched neutral XYZ and 3000-ms increase duration.
The sensor ELF's DT_NEEDED list equals the installed r15 service's list. Before
and after the build, 13 fixed upstream revisions were freshly fetched and all
1,243 project statuses were clean; the temporary Soong builder was restored.
Details are in build-r16-20261107.json and the two r16 upstream-audit reports.

Separate r16 packaging/flash tools keep r15 inputs and outputs unchanged. They
pin all six baseline hashes and the new sensor-service hash, freeze source and
build inputs, preserve filesystem metadata and require an exclusive new output
directory. Scope is one Framework APK and one sensor executable, plus vbmeta.
Python compile and PowerShell parsing passed. The shared filesystem/publication
helpers are unchanged from the completed r15 tests.

The exclusive r16 image directory was published after exact baseline/source
hash rechecks, full filesystem readback, permission/SELinux/UUID verification,
APK certificate validation and AVB descriptor/key verification. Changed-file
sets match exactly the one overlay and one executable; the two replaced
hashtree descriptors are the only vbmeta changes. The frozen spec digest is
200d672ee4f6baa73ca25cf3b803e45ce1b8537d59d274e1c2b8a0b55514ec0c.
Published image identities are recorded in packaging-r16-20261107.json.
Boot and user-visible regression acceptance remain pending at publication.

## Installed r16 and bounded hardware follow-up

r16 reboot completed on slot b, root ADB reconnected, and all six installed
partition hashes match the published chain. The corrected sensor executable
and r15 accepted color-core library match their frozen identities. Installed
Framework resources return increasing-transition 3000 ms and the neutral XYZ.
The actual focused front-CCT probe registered only the non-wake front sensor
and received 5828,6541,7374,8251,9199 K, with no nonpositive delivered Kelvin.
The earlier general probe log is retained separately and is not focused.

The initial two override trials required applied=5300 K and timed out with a
partially warmed applied CCT. A subsequent trial accepts its measured 5840 K
warm baseline. Thirty-five hardware PCC reads show no previous abrupt ~1-second
G/R jump. Small reversals remain (maximum adjacent G/R +0.001770, B/R +0.004547)
in this forced overlapping-fade case; physical natural-ambient acceptance is
still required. Do not treat this as a fully monotonic transition. The bounded
script restores Night Light keys, screen timeout and DWB override to -1.
Temporary display_white_balance_enabled=0 remains until a fresh r17 reboot;
then restore the original absent/default key for user testing.
Evidence: workspace reports/device/r16-runtime/boot-and-installed-hashes.txt,
front-cct-focused-probe.txt, actual-warm-night-transition.txt and
actual-warm-transition-analysis.json. No screen pixels or camera were used.

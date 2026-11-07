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

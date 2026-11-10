# Dolby Voice profile selection

The user reported that Dynamic, Movie and Music worked, but selecting 人声
reported “未能应用，请重新调整此选项” on r40. The AudioEffect command returned
success while the selected profile read back as 4 instead of the requested 8.
This was a selection error, not a reason to suppress the readback warning.

The original sheng Dolby database contains profiles 0–3, spatializer profiles
4–7 and Voice at 8. The original `libdlbdsservice.so` has SHA-256
`ed5c4bd93b0fd3e97f8076c6d07ae2e7ca4ea15156b06d5d3e9788a6ebd57324`.
Its `DsManager::setSelectedProfile` at `0x635c0` reads
`persist.vendor.audio.dolbysurround.enable` and, when it is zero, subtracts 4
from every input greater than 3. Consequently a request for Voice 8 selects
SpatilizerDynamic 4. Its getter reports actual database IDs; parameter and
reset operations also use those IDs directly.

The device-owned `StockDms.setProfile` selects the requested ID, checks the
native result for IDs above 3, and compensates only the verified `ID - 4`
mapping by sending `ID + 4`. The surrounding controller still checks the final
result. Other mismatches and command failures remain errors. Reading the native
result avoids adding vendor-property access to the application domain. The
Voice parameter and reset IDs remain 8, including existing per-profile settings.

References were refreshed on 2026-11-10: piano `seventeen` at
`8c0bb4b9d15ea349eaa09d6de0aa4fec43f7ff41`, LineageOS nuwa at
`8e2b6ca4375919035587115189760eed64f14b8d`, and sm8550-common at
`63da741c41384a23416159f148f7ef7c85c8ea61`. Piano confirms the AudioEffect
protocol and direct per-profile parameters, but its generic selection wrapper
does not compensate for this sheng native remapping. Nuwa/common contain no
matching Voice-selection application fix. These are references only; no
application source was transplanted and the original Dolby libraries were
not modified.

`tools/test_sheng_dolby_profiles.py` compiles the production bridge with a
model of the two verified native branches. It covers every database ID with
surround off, Voice with nonzero surround values, unchanged parameter/reset
IDs, and invalid IDs. `ShengDolbyProfileProbe.java` compiles against the same
bridge and tests the actual tablet without playing audio. All five exposed
profiles read back correctly; Voice's dialog amount is 9 rather than profile
4's amount 4. The final probe restores its initial profile. The earlier
uncorrected probe could not restore a raw spatializer ID through the remapping;
the old app reconciled its requested mode afterward. Both failed and corrected
probe logs are retained.

Raw build, native disassembly and runtime evidence stays under
`reports/device/20261110-resume/dolby/`. The image revision is r41. UI switching
after permanent installation and audible acceptance are recorded separately;
control readback alone does not establish an audible effect.

The normal `ShengDolby` product module, including dexpreopt, passed on
2026-11-10. The API 1 bootstrap compile, DEX 035, v1 signature and original
platform certificate checks also passed; API 1 runtime was not tested. The
scoped r41 package contains that normal module APK, not the separately built
diagnostic APK. Only the APK changed in system_ext; the complete retained AVB
chain and inode metadata checks passed. Full product-image compilation was
not run.

Both r41 partitions were flashed to A and read back with matching hashes.
Android boot completed with the retained 5.15.220 kernel and enforcing policy.
The installed APK hash is
`5b6486ab75dabcb31c91ecca24e9dad4cce4703953c341da0e68404965b6d5ca`.
Original SystemUI remains byte-identical. A read-only effect observer finds
the user's current Dynamic profile 0 enabled, without taking control from the
app. The user confirmed “修好了可以了” on 2026-11-10 and directed work back
to face recognition. This accepts the reported Voice-selection issue;
third-party playback coverage is a separate item.

# sheng hardware status and repair order

Updated 2026-11-07 after the r7 reboot test. All fixes stay in this device tree;
public source is verified against freshly fetched manifest-pinned upstream.
Each logical fix gets a commit, and each batch is compiled, flashed and tested
before moving to the next hardware path. Source changes and static checks alone
are not listed as successful hardware tests.

## Fixed and verified

| Item | Evidence and boundary |
| --- | --- |
| Tablet UI layout | User confirmed normal full-screen tablet layout. |
| Touch and auto-rotation | User confirmed correct touch and orientation; r6 touch/display still work. |
| Six speakers and volume | Six positions audible; volume/mute worked; r5 reboot verified. |
| PCM and compressed offload | Mono/stereo MP3 and stereo AAC playback, pause/resume and volume verified. |
| Dolby and EQ | Real-time switch, modes and EQ verified with six speakers; native four-channel output. |
| Rotating speaker channels | User verified correct left/right in all four orientations, including after r5 reboot. |
| Dolby defaults/text | Unsaved/reset EQ is 0 dB; Chinese mode is 人声; source is already in the tree. |
| Automatic brightness | User confirmed stable output and response to light after the persisted repair. |
| Cover/Hall sleep/wake | User confirmed close-to-sleep/open-to-wake twice after r4. |
| Front light | User confirmed off after removing keyboard/button-backlight activation. |
| Native refresh | Corrected stock submode clocks; native 60/90/120/144 switching checked, and r6 144 Hz touch/display/power-cycle user-verified. |
| Built-in vibration capability | Fake HAL/declaration removed; r6 VibratorManager reports vibratorIds=[]; external devices are not removed. |
| About-device name | r7 Settings name Xiaomi Pad 6S Pro 12.4, display and touch user-verified; scoped hardware model remains 24018RPACC. |
| Recovery basic interaction | Source kernel, touch orientation, ADB and misc access verified in r13. |

## Confirmed working, without claiming a new hardware repair

| Item | Evidence |
| --- | --- |
| Fast charging | User tested the original charger and confirmed normal charging. Computer USB was not a valid fast-charge test. |
| Automatic screen timeout | At the current 15-second setting, PowerManager records timeout sleep and DRM becomes inactive. The earlier setting was ten minutes; charging-stay-awake was configured but mStayOn was false in that snapshot. |

## Remaining work, with simple changes first

| Order | Item | Current state |
| --- | --- | --- |
| Configuration/service integration | NFC/NTAG5 | Tablet uses a passive interconnection tag; stock ntag5_tool/init/policy are missing. Do not advertise unsupported reader/payment NFC. I2C behavior still needs testing. |
| Configuration/service integration | Network location | No network provider is currently bound. Stock MetokNLP has compatible dependency candidates; app/permissions/provider setup and actual location testing remain pending. |
| Component adaptation | Power-button position | Physical button is upper-left; SystemUI's reveal origin is hardcoded on the other edge. No valid RRO side switch exists. Needs device-owned implementation, not a false dimension-only fix. |
| Calibration/service integration | Screen colors and ambient color | Front CCT returns data and is selected; white-balance/TrueTone is not yet enabled and verified. Check primaries, low-light zero samples and stock calibration. |
| Service/backend integration | AON screen attention | Stock MiAONService supports the standard attention interface; APK/VINTF/policy/permissions and camera/QSEE backend still need integration and testing. |
| Driver/HAL integration | Camera | Severe unknown-error report remains; preserve the user's no-capture instruction. |
| Driver/HAL integration | Fingerprint | Enrollment unavailable; existing fingerprint service null-pointer crash remains. |
| Input integration | Keyboard detach/attach | Still reports connected after detaching. |
| Input integration | Stylus | Not yet usable. |
| Audio/Bluetooth integration | LHDC v5 | Not yet verified working. |
| Touch/power integration | Double-tap wake | Still pending. |
| Touch integration | Touch latency and sampling-rate boost | User reports delayed touch and no effect from the higher sampling-rate option; verify actual controller report rate and mode changes separately from touch orientation. |
| Startup | Short backlight-only interval | Recovery/system still show roughly one-to-two seconds of backlight before an image. r6 also had about 52 seconds of framework startup before unlock. |
| Validation | Other sensors | Only individually tested sensors are considered working; remaining sensor tests are pending. |

The user's inventory request does not cancel these remaining fixes. Complete
and verify the simple batch first, then work through the harder items one at a time.

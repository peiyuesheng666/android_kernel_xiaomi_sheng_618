# r20 tablet detection and USB evidence

The user still reports application tablet detection failures after the numeric
model was restored, requests a pleasant marketing-name display in Settings,
and reports intermittent ADB loss at boot and sometimes on screen-off.

Read-only global configuration is 3048x2032 at 400dpi, smallest width 813dp,
screen size xlarge and characteristics tablet. No telephony feature is
declared. Stored Activity configurations for Twelve, Phira and Douyin also
receive sw813dp/xlarge in fullscreen. Settings uses its normal embedded
two-pane layout: the homepage pane has sw443dp and its detail pane sw776dp.
This snapshot does not explain every application's private classification;
an affected foreground app and its actual failure still need identification.
No application data has been cleared and no global density was forced.

Settings' unmodified HardwareInfoPreferenceController directly returns
Build.MODEL. r21 is preparing a resource-only device overlay with separate
marketing name and model number fields in both About and hardware details.
It retains the global numeric model and does not alter public Settings code.

The captured USB event log contains one DISCONNECTED at 11:10:00.389 UTC and
CONNECTED/CONFIGURED at 11:10:01.233/.269, coincident with the agent's explicit
adb root restart. adbd exits cleanly with status0 and starts again. The UDC
is configured, USB data is enabled, both controller runtime states are
active, and the user's separate intermittent screen-off failure has not yet
been captured. Do not count the explicit root restart as its reproduction or
claim that screen-off USB stability is fixed.

Raw evidence is in reports/device/r20-runtime: tablet-detection-state.txt,
activity-configurations.txt, usb-state.txt, logcat-after-user-report.txt,
dmesg-after-user-report.txt and the ongoing usb-observer.txt.

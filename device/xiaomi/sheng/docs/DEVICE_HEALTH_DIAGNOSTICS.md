# Device health diagnostics

Read-only investigation on 2026-11-07 found that DeviceDiagnostics reads
BATTERY_PROPERTY_STATE_OF_HEALTH, whereas the battery settings page can use
full-charge and design capacity. The existing Health HAL returns SOH=0 even
though the stock gauge exposes /sys/class/qcom-battery/soh=93. Both fg1_soh
and fg2_soh also report 93. The aggregate SOH is authoritative for this
device; no capacity-ratio estimate or synthetic sysfs value is used.

The device-owned health executable retains the QTI binary stem, service RC,
IHealth/default version5 manifest and charger suspend behavior. Its main.cpp
is based on the unmodified pinned QTI source (SHA256
fc0e48a388eef1a60217d20191d9cd65667accda4a3b00c04b3a514dc7821a88)
and adds the stock SOH path before BatteryMonitor initialization. The ordinary
system product selects this module; recovery retains the upstream module.
The existing pinned QTI policy already grants the health domain read-only
access to this battery sysfs label; no extra health permissions are added.
Installation, runtime property return and UI acceptance remain
pending. Charge-counter units are a separate unresolved observation.

UFS health_descriptor reports eol_info=0x01 and life_time_estimation_a/b=0x01.
These are coarse JEDEC bins: normal EOL status and 0-10% endurance consumed.
DeviceDiagnostics obtains its storage value from StorageManager/Vold, not
Health HAL storageInfos (which are empty here). Pinned Vold intentionally
maps the first bin to 100% remaining using (max(A,B)-1)*10. This is a
framework display convention, not an exact measured 100% endurance value.
No invented replacement percentage or public-source modification is made.

Raw evidence lives in workspace reports/device/r19-runtime:
health-hal-and-ufs.txt, gauge-state-of-health.txt, health-nodes-and-mount.txt.

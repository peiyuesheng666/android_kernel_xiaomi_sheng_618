# Device health diagnostics

Read-only investigation on 2026-11-07 found that DeviceDiagnostics reads
BATTERY_PROPERTY_STATE_OF_HEALTH, whereas the battery settings page can use
full-charge and design capacity. The existing Health HAL returns SOH=0 even
though the stock gauge exposes /sys/class/qcom-battery/soh=93. Both fg1_soh
and fg2_soh also report 93. The aggregate SOH is authoritative for this
device; no capacity-ratio estimate or synthetic sysfs value is used.

The device-owned health executable has a distinct .sheng filename and init RC.
It uses init override to replace vendor.health-default and vendor.charger,
retaining the original QTI module's IHealth/default version5 manifest and
charger suspend behavior. Keeping the QTI module supplies its original manifest
without duplicate declarations; its normal init services are replaced before
class startup. Its main.cpp
is based on the unmodified pinned QTI source (SHA256
fc0e48a388eef1a60217d20191d9cd65667accda4a3b00c04b3a514dc7821a88)
and adds the stock SOH path before BatteryMonitor initialization. The inherited
unused prop_str declaration is removed so the current -Wall/-Werror build passes. The ordinary
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

## Manufacturing and first-use dates

The stock SecurityCenterPad utility B7.m.e/m passes manufacturing_date and
first_usage_date to miui.util.IMiCharge.getMiChargePath. Stock MiCharge HIDL
method47 reads a named sysfs value; its native fallback appends the requested
name to the battery/class root. Neither date exists under qcom-battery,
power_supply/battery or power_supply/bms on this device. The stock kernel
module's exported attribute inventory also contains no corresponding date.
The standard Health HAL reports both dates as zero. Existing fuel-gauge SOH
does not contain an original first-use date. No reliable serial-date decoder
or independent retained historical date was found, so both dates remain
unknown. Do not substitute ROM installation or first boot for battery history.

Evidence: battery-date-node-inventory.txt, battery-date-exact-paths.txt,
stock-battery-date-strings.json, stock-battery-date-calls.txt and
stock-battery-date-utility.txt. The framework/native disassembly review is
retained in /root/sheng-lineage/battery-date-review-20261107.

The read-only ShengHealthReadback utility calls the same standard properties
used by DeviceDiagnostics. Before r19 it reports SOH status0/value0 and
storage remaining lifetime100, confirming both data paths directly.

## Combined r19 build

The final combined AON/Health build passed on 2026-11-07 (incremental retry
01:28 after removing the unused baseline variable). The prior 13:53 attempt
completed graph and installation checks but failed the unused-variable check.
The new AArch64 executable is 238832 bytes, SHA256
07b3145d9ba4c1b93ad7cb3cfc11ec663a707258b3aeefb50cf6218e3c613011.
Its twelve DT_NEEDED libraries match the retained QTI service. The embedded
SOH path, compiled file label, QTI/ Sheng init override and retained policy
cache markers were checked. Runtime and physical UI acceptance are still pending.

# Remove the unsupported thermal boot-complete wait

The r28 kernel log records a 5000 ms timeout waiting for
/sys/class/thermal/thermal_message/boot_complete in init.sm8550.rc.
The running tablet has no such node; the pinned kernel implementation in
kernel/xiaomi/sm8550/drivers/thermal/mi_thermal_interface.c exports the attribute
group at lines 751–780 without boot_complete. Its supported sconfig node is
present and currently reads 19. mi_thermald and vendor.thermal-hal are running;
thermalservice returns real temperature readings.

Only the unsupported wait and subsequent write are removed. The sys.boot_completed
trigger, qrtr-lookup start and existing sconfig write are retained. No CPU hotplug,
thermal thresholds, throttling, HAL, daemon or public kernel source is changed.
This removes an init action queue stall after sys.boot_completed; it does not
establish a five-second improvement in the earlier boot animation or touch latency.

Validation pending: host init parser, scoped vendor packaging, installed file hash,
boot completion, absence of the exact wait timeout, unchanged thermal services and
sconfig, and existing functionality regression checks. No runtime fix is claimed yet.

## r29 runtime verification

r29 booted on ca10ede3/b and all seven partition/file hashes passed. The exact
boot_complete wait timeout is absent from the new kernel log. mi_thermald and
vendor.thermal-hal remain running, sconfig remains 19, thermalservice reports
temperatures, and the captured crash buffer is empty. No claim is made about
total boot-animation duration. Evidence: runtime-r29-identity-boot-20261108.json.

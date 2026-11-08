# Thermal BCL completion property

r30 kernel evidence records mi_thermald being denied a property-service set of
vendor.sys.thermal.bcl.boot_completed, which has the default vendor property type.
The property remains unset. Evidence: reports/device/r30-20261108-101116/kernel.txt.

The original mi_thermald binary calls property_set with that exact name and the
string "1" at virtual address 0x9c674, after installing its signal handlers and
before entering its pause loop. The existing device policy already grants
mi_thermald set_prop access to vendor_thermal_normal_prop.

Assign only this exact property to that existing type, with boolean validation.
No new allow rule, default-property permission or permissive domain is added.
Keep the thermal configuration and daemon unchanged. Validate the full generated
property contexts against the existing compiled SELinux policy before packaging;
acceptance requires the daemon to publish its own value after reboot under
Enforcing, with the original denial absent. Do not synthesize the value with setprop.

Source implementation is complete; installed/runtime acceptance is pending.

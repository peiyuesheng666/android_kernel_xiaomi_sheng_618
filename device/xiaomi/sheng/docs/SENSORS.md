# sheng sensor and cover configuration

`aidl/sensors` builds the device-owned sensor multihal. The device-orientation
event uses `(orientation + 3) % 4`, matching the user's verified 90-degree
mounting correction. The public `hardware/xiaomi` source remains unchanged.

The module's RC is the single definition of `vendor.sensors-hal-multihal`.
It declares the AIDL interface and preserves the stock audio ultrasound socket,
system UID, groups and scheduling options. The obsolete rootdir override was
removed after r2 boot logs showed init trying to execute the deleted Xiaomi
binary. Starting the sheng HAL temporarily unblocked sensorservice and allowed
system_server to complete boot. The r4 reboot verified the canonical service
started by init with system UID and hal_sensors_default domain, without a
temporary process. Boot completed with SELinux Enforcing.

The built-in display configuration selects the measured front ALS and CCT
sensor names and initializes Android 17 auto-brightness debounce: 4 seconds
for brightening and 8 seconds for darkening, with a 2 lux minimum change. The
manual brightness curve and panel calibration are retained. ALS responded to
the user's flashlight test; the temporary configuration made auto-brightness
stable and responsive to light. CCT binding does not claim white-balance or
panel-color calibration is complete.

The framework RRO enables `config_lidControlsSleep`. The user's cover test
confirmed close-to-sleep and open-to-wake after enabling lid behavior. The
device-owned sensor module, permanent DDC and RRO passed the r4 rebuilt-image
retest: touch/rotation remained correct, two cover close/open cycles worked,
and auto-brightness was stable and responded to a flashlight after reboot.

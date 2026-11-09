#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Bounded use of the stock OTG/CC control, followed by original-value restore.
set -eu
[ "$(id -u)" = 0 ]
grep -q 'sheng_test=hardware-r38 ' /proc/cmdline
node=/sys/class/qcom-battery/cc_toggle
original=$(cat "$node")
[ "$original" = 0 ]
restore() { echo "$original" > "$node"; }
trap restore EXIT
trap 'exit 1' HUP INT TERM
snapshot() {
    echo "phase:$1"
    cat /proc/uptime
    cat "$node"
    echo
    cat /sys/class/power_supply/usb/uevent
    cat /sys/class/android_usb/android0/state
}
snapshot before
echo 1 > "$node"
sleep 3
snapshot cc_enabled
restore
sleep 2
snapshot restored
trap - EXIT

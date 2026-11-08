#!/system/bin/sh
# Read-only USB reference from the known-working recovery, not 6.18 evidence.
uname -a
cat /proc/cmdline
cat /proc/modules
for entry in /sys/bus/platform/devices/*usb* /sys/bus/platform/devices/*dwc* /sys/bus/platform/devices/*phy* /sys/bus/platform/devices/*eud* /sys/bus/platform/devices/*redriver* /sys/bus/platform/devices/*repeater*; do
    [ -e "$entry" ] || continue
    echo "DEVICE $entry"
    readlink -f "$entry/driver"
    readlink -f "$entry/driver/module"
    readlink -f "$entry/of_node"
    cat "$entry/uevent"
    if [ -e "$entry/of_node/compatible" ]; then tr '\000' '\n' < "$entry/of_node/compatible"; fi
    for name in status dr_mode qcom,default-mode qcom,usb-ssphy-mode; do
        if [ -e "$entry/of_node/$name" ]; then echo "$name:"; tr '\000' '\n' < "$entry/of_node/$name"; fi
    done
done
for entry in /sys/class/udc/*; do
    [ -e "$entry" ] || continue
    echo "UDC $entry"
    readlink -f "$entry/device"
    cat "$entry/state"
    cat "$entry/function"
done
cat /sys/kernel/debug/devices_deferred
cat /sys/kernel/debug/usb/devices

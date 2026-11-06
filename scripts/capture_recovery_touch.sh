#!/system/bin/sh
# Exclusively read finger coordinates while keeping the display powered. RAM only.
set -eu
test "$(getprop ro.sheng.recovery.variant)" = r11-native-source-touch
test "$(cat /sys/class/input/event5/device/name)" = NVTCapacitiveTouchScreen
exec /tmp/recovery-touch-capture

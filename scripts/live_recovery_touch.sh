#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Run only in the known temporary recovery; all supplied files live in RAM.
set -eu
test "$(getprop ro.product.device)" = sheng
test "$(getprop ro.sheng.recovery.variant)" = r7-qti-handoff
ram_root=false
while read -r source target filesystem rest; do
    case "$target" in
        /) test "$filesystem" = rootfs; ram_root=true ;;
        /data|/vendor|/odm)
            echo 'A persistent partition is mounted; refusing RAM-only touch test' >&2
            exit 20 ;;
    esac
done </proc/mounts
test "$ram_root" = true
if pidof touch_report_debug >/dev/null; then
    echo 'Touch runtime is already running' >&2
    exit 21
fi
test -c /dev/xiaomi-touch
test -c /dev/input/event5
test -r /vendor/firmware/n81a_nova_thp_config.ini
mkdir -p /vendor/odm/firmware
for model in film_model.tflite water_check.tflite glove_model.tflite; do
    cp "/tmp/sheng-touch-complete/$model" "/vendor/odm/firmware/$model"
    chmod 0644 "/vendor/odm/firmware/$model"
done
chmod 0755 /tmp/sheng-touch-complete/touch_report_debug
nohup runcon u:r:recovery:s0 env LD_LIBRARY_PATH=/tmp/sheng-touch-complete:/system/lib64 \
    /tmp/sheng-touch-complete/touch_report_debug \
    </dev/null >/tmp/sheng-touch-runtime.log 2>&1 &
echo $! >/tmp/sheng-touch-runtime.pid
sleep 3
kill -0 "$(cat /tmp/sheng-touch-runtime.pid)"
cat /tmp/sheng-touch-runtime.pid
head -12 /proc/last_touch_events
cat /tmp/sheng-touch-runtime.log

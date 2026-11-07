#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# The NT36532 supplies frames; this board's stock runtime produces input events.
exec >>/tmp/sheng-touch-runtime.log 2>&1
remaining=30
while [ ! -c /dev/xiaomi-touch ] && [ "$remaining" -gt 0 ]; do
    sleep 1
    remaining=$((remaining - 1))
done
test -c /dev/xiaomi-touch || exit 1
for file in /vendor/firmware/n81a_nova_thp_config.ini \
    /odm/firmware/film_model.tflite /odm/firmware/water_check.tflite \
    /odm/firmware/glove_model.tflite; do
    test -r "$file" || { echo "Missing sheng touch input: $file"; exit 1; }
done
export LD_LIBRARY_PATH=/system/lib64
exec /system/bin/touch_report_debug

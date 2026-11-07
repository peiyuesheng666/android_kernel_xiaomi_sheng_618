#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Firmware is mounted read-only by init before ADSP is requested. Keep the
# mount independent of /vendor, which recovery may mount and unmount later.
exec >> /tmp/sheng-recovery-hardware.log 2>&1
echo "sheng recovery hardware: $(date)"
if [ ! -r /firmware/image/adsp.mdt ] || [ ! -r /firmware/image/adsp.b01 ]; then
    echo "ADSP firmware unavailable; not starting a partially supplied DSP"
    exit 1
fi
for remote in /sys/class/remoteproc/remoteproc*; do
    [ -r "$remote/name" ] || continue
    case "$(cat "$remote/name")" in
        *adsp*)
            if [ "$(cat "$remote/state")" = offline ]; then
                echo start > "$remote/state" || exit 1
            fi
            echo "$remote: $(cat "$remote/state")"
            ;;
    esac
done

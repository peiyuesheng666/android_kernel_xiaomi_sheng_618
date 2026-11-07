#!/system/bin/sh
# Bounded temporary library trial. The on-disk r13 image is never written.
set -eu
candidate=/data/local/tmp/sheng-color-owned-20261107/libsdmcore.so
target=/vendor/lib64/libsdmcore.so
state=/data/local/tmp/sheng-color-owned-20261107/state.txt
service=vendor.qti.hardware.display.composer
baseline=5f7226abc1ef594fb7e15e89bbf54ee835d49001cefad777182ae8b7a229cb03
expected=${1:?Expected candidate SHA256 required}
duration=${2:-90}
[ "${#duration}" -le 3 ]
case "$duration" in ''|*[!0-9]*) exit 1;; esac
[ "$duration" -ge 30 ] && [ "$duration" -le 300 ]
[ "${#expected}" -eq 64 ]
case "$expected" in *[!0-9a-f]*) exit 1;; esac
[ "$(id -u)" = 0 ]
[ "$(getprop ro.product.device)" = sheng ]
[ "$(getprop ro.boot.slot_suffix)" = _b ]
[ -f "$candidate" ] && [ ! -L "$candidate" ]
[ "$(readlink -f "$candidate")" = "$candidate" ]
[ "$(sha256sum "$candidate" | cut -d ' ' -f 1)" = "$expected" ]
[ "$(nsenter -t 1 -m -- sha256sum "$target" | cut -d ' ' -f 1)" = "$baseline" ]
if grep -F " $target " /proc/1/mountinfo; then
    echo 'Existing target mount; refusing to replace it' >&2
    exit 1
fi
chmod 0644 "$candidate"
chcon u:object_r:vendor_file:s0 "$candidate"
old_pid=$(pidof vendor.qti.hardware.display.composer-service-sheng)
[ -n "$old_pid" ]
mounted=0
mount_id=
cleanup() {
    trap - EXIT HUP INT TERM
    if [ "$mounted" = 1 ]; then
        current_id=$(awk -v path="$target" '$5 == path {print $1}' /proc/1/mountinfo)
        if [ -n "$mount_id" ] && [ "$current_id" = "$mount_id" ]; then
            nsenter -t 1 -m -- umount "$target" ||
                nsenter -t 1 -m -- umount -l "$target"
            [ "$(nsenter -t 1 -m -- sha256sum "$target" | cut -d ' ' -f 1)" = "$baseline" ]
            setprop ctl.restart "$service"
            echo "ROLLED_BACK baseline=$baseline" | tee -a "$state"
        else
            echo 'Mount identity changed; refusing to unmount another layer' | tee -a "$state"
            exit 1
        fi
    fi
}
trap cleanup EXIT HUP INT TERM
nsenter -t 1 -m -- mount --bind "$candidate" "$target"
mounted=1
mount_id=$(awk -v path="$target" '$5 == path {print $1}' /proc/1/mountinfo)
[ -n "$mount_id" ]
[ "$(nsenter -t 1 -m -- sha256sum "$target" | cut -d ' ' -f 1)" = "$expected" ]
echo "START old_pid=$old_pid candidate=$expected mount=$mount_id duration=$duration" > "$state"
setprop ctl.restart "$service"
new_pid=
stable=0
i=0
while [ "$i" -lt "$duration" ]; do
    sleep 1
    i=$((i + 1))
    pid=$(pidof vendor.qti.hardware.display.composer-service-sheng || true)
    if [ -z "$new_pid" ]; then
        if [ -n "$pid" ] && [ "$pid" != "$old_pid" ]; then
            new_pid=$pid
        elif [ "$i" -ge 20 ]; then
            echo 'FAILED no new composer after 20 seconds' | tee -a "$state"
            exit 1
        fi
    elif [ "$pid" != "$new_pid" ]; then
        echo "FAILED composer changed old=$new_pid current=$pid" | tee -a "$state"
        logcat -d -b crash -v brief -t 100
        exit 1
    else
        stable=$((stable + 1))
        if [ "$stable" = 10 ]; then
            echo "READY stable_pid=$pid" | tee -a "$state"
        fi
    fi
done
echo 'TRIAL_COMPLETE restoring r13 library' | tee -a "$state"

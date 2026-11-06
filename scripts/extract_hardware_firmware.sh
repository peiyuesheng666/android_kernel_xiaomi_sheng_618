#!/usr/bin/env bash
set -euo pipefail
root=/root/sheng-lineage/firmware-dump/hardware
for partition in dsp modem bluetooth; do
    image="$root/firmware-images/$partition.img"
    target="$root/firmware-files/$partition"
    mount_dir="$root/mounts/$partition"
    [[ ! -f "$root/firmware-files/.$partition.complete" ]] || continue
    mkdir -p "$target" "$mount_dir"
    if ! mountpoint -q "$mount_dir"; then
        if [[ "$partition" == dsp ]]; then
            mount -t ext4 -o loop,ro,noload,nodev,nosuid,noexec "$image" "$mount_dir"
        else
            mount -t vfat -o loop,ro,nodev,nosuid,noexec "$image" "$mount_dir"
        fi
    fi
    cp -a "$mount_dir/." "$target/"
    umount "$mount_dir"
    touch "$root/firmware-files/.$partition.complete"
    echo "Extracted $partition firmware files"
done

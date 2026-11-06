#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C LANG=C
root=/root/sheng-lineage/firmware-dump
mkdir -p "$root/mounts" "$root/partitions"
# Only mount extracted copies on C:, never the firmware input on E:.
for partition in vendor odm vendor_dlkm system_dlkm system system_ext product mi_ext; do
    image="$root/images/${partition}_a.img"
    mount_dir="$root/mounts/$partition"
    target="$root/partitions/$partition"
    marker="$root/partitions/.${partition}.complete"
    [[ ! -f "$marker" ]] || continue
    mkdir -p "$mount_dir" "$target"
    if ! mountpoint -q "$mount_dir"; then
        mount -t erofs -o loop,ro,nodev,nosuid,noexec "$image" "$mount_dir"
    fi
    cp -a -- "$mount_dir/." "$target/"
    umount "$mount_dir"
    touch "$marker"
    echo "Extracted filesystem $partition"
done

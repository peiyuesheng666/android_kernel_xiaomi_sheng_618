#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C LANG=C
root=/root/sheng-lineage
swap=/root/sheng-612/lineage-build.swap
mkdir -p "$root"/{lineage-24.0,logs,firmware-dump,artifacts}
# Ubuntu's native ext4 filesystem is backed by the C: VHDX.
[[ $(findmnt -n -o FSTYPE -T "$root") == ext4 ]] || {
    echo 'Expected the native WSL ext4 filesystem' >&2; exit 1;
}
if [[ ! -e "$swap" ]]; then
    fallocate -l 48G "$swap"
    chmod 600 "$swap"
    mkswap "$swap"
fi
if ! python3 - "$swap" <<'PY'
import sys
with open('/proc/swaps') as f:
    active = [line.split()[0] for line in f.readlines()[1:]]
sys.exit(0 if sys.argv[1] in active else 1)
PY
then
    swapon --priority 0 "$swap"
fi
extra_swap=/root/sheng-lineage/lineage-extra.swap
if [[ ! -e "$extra_swap" ]]; then
    fallocate -l 20G "$extra_swap"
    chmod 600 "$extra_swap"
    mkswap "$extra_swap"
fi
if ! python3 - "$extra_swap" <<'PY'
import sys
with open('/proc/swaps') as f:
    active = [line.split()[0] for line in f.readlines()[1:]]
sys.exit(0 if sys.argv[1] in active else 1)
PY
then
    swapon --priority 0 "$extra_swap"
fi
printf 'WSL build filesystem\n'
df -h "$root" /mnt/c
printf 'Active swap\n'
swapon --show
free -h

#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=/root/sheng-lineage
exec 8>"$root/logs/continuation.lock"
flock -n 8 || { echo 'An existing sync/build continuation owns the lock' >&2; exit 1; }
printf 'repairing-shallow-toolchains\n' > "$root/logs/rom-status.txt"
python3 "$here/repair_shallow_toolchains.py"
if [[ -f "$root/logs/repo-sync-24-1.log" ]]; then
    mv -- "$root/logs/repo-sync-24-1.log" "$root/logs/repo-sync-24-before-shallow-repair-$(date +%Y%m%d-%H%M%S).log"
fi
flock -u 8
exec 8>&-
exec bash "$here/continue_after_sync.sh"

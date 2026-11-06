#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=/root/sheng-lineage
mkdir -p "$root/logs"
[[ ! -f "$root/logs/source-maintenance.pending" ]] || {
    echo 'Source/cache maintenance is in progress; do not start another build' >&2; exit 75;
}
exec 9>"$root/logs/build.lock"
flock -n 9 || { echo 'A sheng build is already running' >&2; exit 1; }
exec python3 "$here/build_events.py" --state-dir "$root/logs" --disk-path /mnt/c --min-free-gib 20 run -- bash "$here/build_lineage_worker.sh"

#!/usr/bin/env bash
# Validate device-specific blockers before spending time on the complete ROM.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=/root/sheng-lineage
mkdir -p "$root/logs"
[[ ! -f "$root/logs/source-maintenance.pending" ]] || exit 75
exec 9>"$root/logs/build.lock"
flock -n 9 || { echo 'A sheng build or validation is already running' >&2; exit 1; }
exec python3 "$here/build_events.py" --state-dir "$root/logs" --disk-path /mnt/c --min-free-gib 20 run -- bash "$here/validate_lineage_worker.sh"

#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=/root/sheng-lineage
rom="$root/lineage-24.0"
printf 'preparing\n' > "$root/logs/build-phase.txt"
printf 'preparing\n' > "$root/logs/build-status.txt"
bash "$here/setup_rom_workspace.sh"
source "$here/rom_build_settings.sh"
[[ ! -f "$root/logs/device-audit.pending" ]] || {
    echo 'Device preparation audit is still in progress' >&2; exit 1;
}
[[ $(cat "$root/logs/rom-status.txt") == synced ]] || {
    echo 'Finish source/dependency synchronization before building' >&2; exit 1;
}
python3 "$here/preflight_sheng.py" --require-synced
python3 "$here/require_validated.py"
cd "$rom"
printf 'configuring\n' > "$root/logs/build-phase.txt"
printf 'configuring\n' > "$root/logs/build-status.txt"
set +u
source build/envsetup.sh
lunch lineage_sheng-cp2a-userdebug
set -u
printf 'building\n' > "$root/logs/build-phase.txt"
printf 'building\n' > "$root/logs/build-status.txt"
if m bacon -j"$SHENG_BUILD_JOBS" > "$root/logs/build-lineage.log" 2>&1; then
    printf 'compiled\n' > "$root/logs/build-status.txt"
    printf 'exporting\n' > "$root/logs/build-phase.txt"
    python3 "$here/export_lineage.py"
    printf 'exported\n' > "$root/logs/build-phase.txt"
    printf 'exported\n' > "$root/logs/build-status.txt"
else
    result=$?
    printf 'failed:%s\n' "$result" > "$root/logs/build-status.txt"
    echo "Build exited with code $result; diagnostics are in $root/logs/build-lineage.log" >&2
    exit "$result"
fi

#!/usr/bin/env bash
set -euo pipefail
root=/root/sheng-lineage
rom="$root/lineage-24.0"
archive="$root/archive/pre-standalone"
mkdir -p "$archive" "$rom/vendor/xiaomi"
# Archive only our previous generated outputs. Never remove the stock input,
# kernel repositories, or another user's project.
if [[ ! -f "$archive/installed.marker" ]]; then
    for relative in device/xiaomi/sheng vendor/xiaomi/sheng vendor/xiaomi/sm8550-common; do
        source="$rom/$relative"
        target="$archive/${relative//\//_}"
        if [[ -d "$source" ]]; then
            [[ ! -e "$target" ]] || { echo "Archive already exists: $target" >&2; exit 1; }
            mv -- "$source" "$target"
        fi
    done
    touch "$archive/installed.marker"
fi
mkdir -p "$rom/vendor/xiaomi/sheng"
cp -a "$root/extraction-standalone/vendor/xiaomi/sheng/." "$rom/vendor/xiaomi/sheng/"
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "$here/install_rom_configuration.sh"

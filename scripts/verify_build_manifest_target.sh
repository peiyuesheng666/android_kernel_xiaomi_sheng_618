#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=/root/sheng-lineage
exec 9>"$root/logs/build.lock"
flock -n 9 || { echo 'Another build is running' >&2; exit 1; }
source "$here/rom_build_settings.sh"
cd "$root/lineage-24.0"
set +u
source build/envsetup.sh
lunch lineage_sheng-cp2a-userdebug
set -u
m -j"$SHENG_BUILD_JOBS" build-manifest.xml > "$root/logs/verify-build-manifest-target.log" 2>&1
python3 -c "import xml.etree.ElementTree as ET; assert ET.parse('out/target/product/sheng/product/etc/build-manifest.xml').getroot().tag == 'manifest'; print('Sandboxed build-manifest.xml target passed and XML parsed')"

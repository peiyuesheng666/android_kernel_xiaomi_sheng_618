#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=/root/sheng-lineage
rom="$root/lineage-24.0"
log="$root/logs/recovery-qti"
mkdir -p "$log"
exec 9>"$root/logs/build.lock"
flock -n 9 || { echo 'Another source build holds the lock'; exit 1; }
printf 'preparing-qti-recovery\n' > "$log/build-phase.txt"
bash "$here/setup_rom_workspace.sh" > "$log/workspace.log" 2>&1
source "$here/rom_build_settings.sh"
bash "$here/install_rom_configuration.sh"
cd "$rom"
set +u
source build/envsetup.sh
lunch lineage_sheng-cp2a-userdebug
set -u
printf 'building-qti-recovery-binary\n' > "$log/build-phase.txt"
m -j"$SHENG_BUILD_JOBS" recovery > "$log/build.log" 2>&1
python3 - <<'PY'
import json
from pathlib import Path
v = json.loads(Path('out/soong/soong.lineage_sheng.variables').read_text())
assert v['VendorVars']['recovery']['target_recovery_uses_qti_drm'] in ('true', True)
assert v['VendorVarTypes']['recovery']['target_recovery_uses_qti_drm'] == 'bool'
PY
candidate="$root/recovery-qti-candidate"
mkdir -p "$candidate"
cp -p out/target/product/sheng/recovery/root/system/bin/recovery "$candidate/recovery-qti"
sha256sum "$candidate/recovery-qti" > "$candidate/SHA256SUMS"
printf 'qti-recovery-binary-compiled\n' > "$log/build-phase.txt"
echo "QTI recovery candidate compiled at $candidate; no ROM or device partition was flashed"

#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$here/prepare_sheng_stock.py"
bash "$here/extract_sheng_vendor.sh"
bash "$here/install_standalone_vendor.sh"
python3 "$here/verify_dolby.py"
python3 "$here/preflight_sheng.py"
# This releases preparation only. Full Soong/SELinux/VINTF/kernel-ABI and
# hardware tests remain pending and are not replaced by these scoped checks.
rm -f -- /root/sheng-lineage/logs/device-audit.pending
printf 'Device preparation checks passed; actual Android build and runtime tests remain pending.\n'

#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$here/prepare_dolby.py"
python3 "$here/prepare_sheng_stock.py"
bash "$here/extract_sheng_vendor.sh"
bash "$here/install_standalone_vendor.sh"
rom=/root/sheng-lineage/lineage-24.0
if [[ -f "$rom/out/soong/installs-lineage_sheng.mk" ]]; then
    (
        cd "$rom"
        TARGET_PRODUCT=lineage_sheng TARGET_RELEASE=cp2a TARGET_BUILD_VARIANT=userdebug \
            bash build/soong/soong_ui.bash --dumpvar-mode PRODUCT_COPY_FILES \
            > /root/sheng-lineage/logs/product-copy-files.txt
    )
    python3 "$here/audit_install_collisions.py" --require-clean
fi
exec python3 "$here/resume_after_source_maintenance.py"

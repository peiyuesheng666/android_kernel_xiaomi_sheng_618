#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/scripts/build-env.sh"
if [ "${1:-}" = --help ]; then echo 'Usage: bash mkbootimage.sh [--stock-boot /path/to/boot.img]'; exit 0; fi
stock_boot=${STOCK_BOOT:-}
case "$#" in
  0) ;;
  1) stock_boot=$1;;
  2) [ "$1" = --stock-boot ] || { echo 'Use --stock-boot /path/to/boot.img'; exit 2; }; stock_boot=$2;;
  *) echo 'Usage: bash mkbootimage.sh [--stock-boot /path/to/boot.img]'; exit 2;;
esac
if [ -z "$stock_boot" ]; then
  for candidate in "$PROJECT_ROOT/stock-boot.img" "${PROJECT_ROOT}-deps/sheng-stock-boot.img" "$BUILD_ROOT/stock-boot.img"; do
    if [ -f "$candidate" ]; then stock_boot=$candidate; break; fi
  done
fi
[ -n "$stock_boot" ] && [ -f "$stock_boot" ] || { echo 'Provide stock-boot.img in the project root or use --stock-boot /path/to/boot.img'; exit 2; }
stock_boot=$(realpath -- "$stock_boot")
start_stage mkbootimage "$@"
require_commands jq sha256sum gzip
require_kernel
[ -f "$output/.embed-ready.json" ] && [ -f "$output/build-result.json" ] || { echo 'Run bash embed.sh first.'; exit 2; }
[ "$(sha256sum "$output/Image" | cut -d' ' -f1)" = "$(jq -r .image_sha256 "$output/.embed-ready.json")" ] || { echo 'Image changed; rerun embed.sh.'; exit 2; }
[ "$(sha256sum "$stock_boot" | cut -d' ' -f1)" = 4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea ] || { echo 'Stock boot template does not match sheng OS3.0.303.0'; exit 1; }
bash "$PROJECT_ROOT/tools/pack-boot.sh" "$output/Image" "$stock_boot" "$output"
jq --arg boot "$(sha256sum "$output/boot.img" | cut -d' ' -f1)" \
  '.boot_packaged = true | .artifacts["boot.img"] = $boot' "$output/build-result.json" > "$output/build-result.tmp"
mv "$output/build-result.tmp" "$output/build-result.json"
publish_result
echo "Boot image packed: $dist/boot.img"

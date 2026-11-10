#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [ "${1:-}" = --help ]; then echo 'Usage: bash build.sh [--stock-boot /path/to/boot.img] [--config-only]'; exit 0; fi
case "$#" in
  0) ;;
  1) [ "$1" = --config-only ] || { echo 'Use --stock-boot /path/to/boot.img or --config-only'; exit 2; };;
  2) [ "$1" = --stock-boot ] || { echo 'Use --stock-boot /path/to/boot.img'; exit 2; };;
  *) echo 'Usage: bash build.sh [--stock-boot /path/to/boot.img] [--config-only]'; exit 2;;
esac
. "$here/scripts/project-env.sh"
if [ "${1:-}" != --config-only ]; then
  stock_boot=${STOCK_BOOT:-}
  if [ "$#" = 2 ]; then stock_boot=$2; fi
  [ -n "$stock_boot" ] && [ -f "$stock_boot" ] || {
    echo 'Provide stock-boot.img in the root or use bash build.sh --stock-boot /path/to/boot.img'; exit 2;
  }
fi
if [ "${K618_LIMITS_VERIFIED:-}" != 1 ]; then
  exec "$PYTHON" "$here/scripts/limit-run.py" bash "$here/build.sh" "$@"
fi
if [ "${1:-}" = --config-only ]; then exec bash "$here/buildkernel.sh" --config-only; fi
# Each stage is also directly runnable from the project root.
bash "$here/buildkernel.sh"
bash "$here/buildmodules.sh"
bash "$here/embed.sh"
bash "$here/mkbootimage.sh" "$@"

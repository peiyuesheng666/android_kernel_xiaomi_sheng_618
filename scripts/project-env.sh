#!/usr/bin/env bash
# Source from Linux/WSL; keep downloaded sources and outputs outside the project.
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
account_home=$(getent passwd "$(id -un)" | cut -d: -f6)
BUILD_ROOT=$(realpath -m -- "${BUILD_ROOT:-$account_home/sheng-kernel-build}")
case "$BUILD_ROOT" in /|/root|/home|"$account_home"|/mnt/*)
  echo "Choose a native Linux BUILD_ROOT: $BUILD_ROOT" >&2
  return 2 2>/dev/null || exit 2;;
esac
case "$BUILD_ROOT/" in "$PROJECT_ROOT/"*)
  echo 'BUILD_ROOT must be outside PROJECT_ROOT' >&2
  return 2 2>/dev/null || exit 2;;
esac
case "$BUILD_ROOT$PROJECT_ROOT" in *[[:space:]]*)
  echo 'Use project/build paths without whitespace' >&2
  return 2 2>/dev/null || exit 2;;
esac
export PROJECT_ROOT BUILD_ROOT
export K618="$BUILD_ROOT/k618"
default_prebuilts=$K618/ws/prebuilts
default_elfutils=$BUILD_ROOT/host-tools/elfutils-0.193
if [ -d "${PROJECT_ROOT}-deps/prebuilts" ]; then default_prebuilts=${PROJECT_ROOT}-deps/prebuilts; fi
if [ -d "${PROJECT_ROOT}-deps/elfutils-0.193" ]; then default_elfutils=${PROJECT_ROOT}-deps/elfutils-0.193; fi
export PREBUILTS="${PREBUILTS:-$default_prebuilts}"
export ELFUTILS="${ELFUTILS:-$default_elfutils}"
if [ -z "${STOCK_BOOT:-}" ]; then
  for stock_candidate in "$PROJECT_ROOT/stock-boot.img" "${PROJECT_ROOT}-deps/sheng-stock-boot.img" "$BUILD_ROOT/stock-boot.img"; do
    if [ -f "$stock_candidate" ]; then STOCK_BOOT=$stock_candidate; break; fi
  done
fi
export STOCK_BOOT="${STOCK_BOOT:-}"
export PYTHON="${PYTHON:-python3.11}"
export JOBS="${JOBS:-4}" TAG="${TAG:-walt-charge-20261114}"
[[ "$JOBS" =~ ^[1-9][0-9]*$ && "$JOBS" -le 4 ]] || { echo 'JOBS must be 1..4' >&2; return 2 2>/dev/null || exit 2; }
[[ "$TAG" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid TAG' >&2; return 2 2>/dev/null || exit 2; }

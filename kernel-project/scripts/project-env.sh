#!/usr/bin/env bash
# Source from Linux/WSL; keep downloaded sources and outputs outside the project.
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
account_home=$(getent passwd "$(id -un)" | cut -d: -f6)
BUILD_ROOT=$(realpath -m -- "${BUILD_ROOT:-$account_home/sheng-618-project-build}")
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
export PREBUILTS="${PREBUILTS:-$K618/ws/prebuilts}"
export ELFUTILS="${ELFUTILS:-$BUILD_ROOT/host-tools/elfutils-0.193}"
export PYTHON="${PYTHON:-python3.11}"
export JOBS="${JOBS:-4}" TAG="${TAG:-release-r70}"
[[ "$JOBS" =~ ^[1-9][0-9]*$ && "$JOBS" -le 4 ]] || { echo 'JOBS must be 1..4' >&2; return 2 2>/dev/null || exit 2; }
[[ "$TAG" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid TAG' >&2; return 2 2>/dev/null || exit 2; }

#!/usr/bin/env bash
# Compatibility with scripts/run-limited.sh build.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec bash "$here/build.sh" "$@"

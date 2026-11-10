#!/usr/bin/env bash
# The release ships an exact adapted source cache; bootstrap is offline.
set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/project-env.sh"
exec bash "$PROJECT_ROOT/scripts/prepare.sh" "$@"

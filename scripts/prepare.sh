#!/usr/bin/env bash
set -euo pipefail
[ "${K618_LIMITS_VERIFIED:-}" = 1 ] || { echo 'Use scripts/run-limited.sh prepare'; exit 2; }
. "$(dirname -- "${BASH_SOURCE[0]}")/project-env.sh"
exec "$PYTHON" "$PROJECT_ROOT/scripts/prepare-inputs.py" "$@"

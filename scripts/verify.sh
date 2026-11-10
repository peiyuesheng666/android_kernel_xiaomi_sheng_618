#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/project-env.sh"
exec "$PYTHON" "$PROJECT_ROOT/scripts/verify.py" "$@"

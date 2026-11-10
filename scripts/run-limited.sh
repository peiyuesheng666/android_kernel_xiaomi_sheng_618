#!/usr/bin/env bash
# Same public action names as the Xiaomi 13 Pro reference project.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
action=${1:-}
case "$action" in bootstrap|prepare|build|verify) ;; *)
  echo 'Usage: bash scripts/run-limited.sh bootstrap|prepare|build|verify'; exit 2;;
esac
shift
. "$here/project-env.sh"
exec "$PYTHON" "$here/limit-run.py" bash "$here/$action.sh" "$@"

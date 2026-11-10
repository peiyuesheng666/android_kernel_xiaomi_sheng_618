#!/usr/bin/env bash
# Same public action names as the Xiaomi 13 Pro reference project.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
action=${1:-}
case "$action" in bootstrap|prepare|build|verify|buildkernel|buildmodules|embed|mkbootimage) ;; *)
  echo 'Usage: bash scripts/run-limited.sh bootstrap|prepare|build|verify|buildkernel|buildmodules|embed|mkbootimage'; exit 2;;
esac
shift
. "$here/project-env.sh"
case "$action" in
  buildkernel|buildmodules|embed|mkbootimage) target=$PROJECT_ROOT/$action.sh;;
  *) target=$here/$action.sh;;
esac
exec "$PYTHON" "$here/limit-run.py" bash "$target" "$@"

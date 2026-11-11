#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/build-env.sh"
require_prepared
for suite in test-charging-callbacks test-charging-special test-pps-auto; do
  "$PYTHON" "$PROJECT_ROOT/scripts/$suite.py"
done

#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "$here/setup_rom_workspace.sh"
exec bash "$here/sync_lineage.sh"

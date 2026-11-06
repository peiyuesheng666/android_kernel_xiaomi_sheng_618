#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=/root/sheng-lineage
mkdir -p "$root/logs"
exec 8>"$root/logs/continuation.lock"
flock -n 8 || { echo 'A source sync/build continuation already exists' >&2; exit 1; }
bash "$here/setup_rom_workspace.sh"
cd "$root/lineage-24.0"
[[ $(git config -f .repo/manifests.git/config branch.default.merge) == refs/heads/lineage-24.0 ]] || {
    echo 'Initialize the 24.0 manifest before starting this pipeline' >&2; exit 1;
}
printf 'syncing-24\n' > "$root/logs/rom-status.txt"
export GIT_TERMINAL_PROMPT=0 REPO_ALLOW_SHALLOW=1
for attempt in 1 2 3; do
    if repo sync -c --force-sync --no-clone-bundle --no-tags --optimized-fetch -j6 \
        > "$root/logs/repo-sync-24-${attempt}.log" 2>&1; then
        printf 'synced\n' > "$root/logs/rom-status.txt"
        repo manifest -r -o "$root/logs/source-manifest.xml"
        exec bash "$here/build_lineage.sh"
    fi
done
printf 'sync-failed-24\n' > "$root/logs/rom-status.txt"
echo '24.0 sync failed after retries; inspect repo-sync-24 logs' >&2
exit 1

#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C LANG=C
export GIT_TERMINAL_PROMPT=0
export REPO_ALLOW_SHALLOW=1
root=/root/sheng-lineage
[[ -d "$root/lineage-24.0" ]] || { echo 'Run setup_rom_workspace.sh first' >&2; exit 1; }
cd "$root/lineage-24.0"
mkdir -p "$root/logs"
if [[ ! -d .repo/manifests.git ]]; then
    repo init -u https://github.com/LineageOS/android.git -b lineage-24.0 \
        --depth=1 --no-clone-bundle --git-lfs > "$root/logs/repo-init.log" 2>&1
fi
printf 'syncing\n' > "$root/logs/rom-status.txt"
repo sync -c --force-sync --no-clone-bundle --no-tags --optimized-fetch -j6 \
    > "$root/logs/repo-sync.log" 2>&1
GIT_TERMINAL_PROMPT=0 git -C external/chromium-webview/prebuilt/arm64 lfs pull \
    --include=webview.apk --exclude= > "$root/logs/webview-lfs.log" 2>&1
printf 'synced\n' > "$root/logs/rom-status.txt"
repo manifest -r -o "$root/logs/source-manifest.xml"
echo 'LineageOS platform sync complete'

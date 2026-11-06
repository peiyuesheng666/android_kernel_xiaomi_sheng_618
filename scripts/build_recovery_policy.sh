#!/usr/bin/env bash
set -euo pipefail
root=/root/sheng-lineage
rom="$root/lineage-24.0"
exec 9>"$root/logs/build.lock"
flock -n 9 || { echo 'Another build holds the lock'; exit 1; }
cd "$rom"
# Existing Ninja rules list these policy inputs explicitly. Rebuild only the
# recovery policy and its dependency checks, without another whole ROM build.
prebuilts/build-tools/linux-x86/bin/ninja -f out/combined-lineage_sheng.ninja -j24 \
    out/target/product/sheng/recovery/root/sepolicy \
    >"$root/logs/recovery-touch-policy.log" 2>&1

#!/usr/bin/env bash
set -euo pipefail
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null
root=/root/sheng-612
mkdir -p "$root"/{src,tools,toolchains,out,logs,stock}
if [[ ! -d "$root/src/common/.git" ]]; then
    git clone --depth=1 --single-branch --branch android16-6.12 \
        https://android.googlesource.com/kernel/common "$root/src/common"
fi
git -C "$root/src/common" rev-parse HEAD
git -C "$root/src/common" status --short
head -n 7 "$root/src/common/Makefile"
cat "$root/src/common/build.config.constants"

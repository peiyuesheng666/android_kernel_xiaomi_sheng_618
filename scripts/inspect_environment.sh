#!/usr/bin/env bash
set -euo pipefail
for p in /AGENTS.md /root/AGENTS.md; do
    if [[ -f "$p" ]]; then printf 'INSTRUCTIONS %s\n' "$p"; cat "$p"; fi
done
for p in /root/sheng_kernel /root/kernel-lineage /root/sheng /root/sheng-gh; do
    printf 'DIRECTORY %s\n' "$p"
    if [[ -d "$p" ]]; then
        find "$p" -maxdepth 2 -type d \( -name 'clang*' -o -name 'rust*' -o -name 'prebuilts' -o -name 'kernel_platform' -o -name '.git' -o -name 'tools' \) -print | head -n 25
    fi
done
printf 'Existing official toolchain candidates\n'
find /root/sheng_kernel /root/kernel-lineage /root/sheng /root/sheng-gh -maxdepth 5 -name AndroidVersion.txt -print 2>/dev/null | head -n 20
printf 'Machine\n'
df -h /root/sheng-618-project-build /mnt/c /mnt/e
free -h
printf 'Relevant commands\n'
command -v python3 curl git make flex bison bc pahole cpio dtc lz4 zstd debugfs simg2img fsck.erofs dump.erofs depmod modinfo || true

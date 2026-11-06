#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C LANG=C
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root=/root/sheng-lineage
sandbox="$root/extraction-standalone"
mkdir -p "$sandbox/tools" "$sandbox/device/xiaomi" "$sandbox/prebuilts/extract-tools/linux-x86/bin"
cp -a "$root/tools/extract-utils" "$sandbox/tools/"
mkdir -p "$sandbox/device/xiaomi/sheng"
cp -a "$here/device/xiaomi/sheng/." "$sandbox/device/xiaomi/sheng/"
# Use official LineageOS patchelf and the already-pinned Google LLVM tools.
patchelf="$sandbox/prebuilts/extract-tools/linux-x86/bin/patchelf-0_18"
if [[ ! -e "$patchelf" ]]; then
    curl -fL --retry 3 --max-time 120 \
        https://raw.githubusercontent.com/LineageOS/android_prebuilts_extract-tools/lineage-23.2/linux-x86/bin/patchelf-0_18 \
        -o "$patchelf"
    chmod 755 "$patchelf"
fi
llvm="$sandbox/prebuilts/clang/host/linux-x86/llvm-binutils-stable"
mkdir -p "$llvm"
for name in llvm-strip llvm-objdump; do
    ln -sfn "/root/sheng-612/toolchains/clang-r536225/bin/$name" "$llvm/$name"
done
cd "$sandbox"
python3 device/xiaomi/sheng/extract-files.py "$root/firmware-dump/extract-source" \
    > "$root/logs/vendor-extraction.log" 2>&1
python3 "$here/scripts/export_gsl_headers.py" --vendor-tree "$sandbox/vendor/xiaomi/sheng"
echo 'Vendor extraction and makefile generation complete'

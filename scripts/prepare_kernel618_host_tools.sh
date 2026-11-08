#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Private host libraries; do not replace Ubuntu or the active ROM toolchain.
set -euo pipefail
root=/root/sheng-618
version=0.193
sha=7857f44b624f4d8d421df851aaae7b1402cfe6bcdd2d8049f15fc07d3dde7635
prefix="${SHENG_ELFUTILS_PREFIX:-$root/host-tools/elfutils-$version}"
archive="$root/host-tools/src/elfutils-$version.tar.bz2"
source_dir="${archive%.tar.bz2}"
mkdir -p "$(dirname "$archive")" "$root/logs"
if [[ ! -f "$archive" ]]; then
    curl -fsSL --retry 2 "https://sourceware.org/elfutils/ftp/$version/elfutils-$version.tar.bz2" -o "$archive.download"
    printf '%s  %s\n' "$sha" "$archive.download" | sha256sum --check
    mv -- "$archive.download" "$archive"
fi
printf '%s  %s\n' "$sha" "$archive" | sha256sum --check
if [[ -f "$prefix/.sheng-host-tools-complete" ]]; then
    [[ $(cat "$prefix/.sheng-host-tools-complete") == "$sha" ]]
    exit 0
fi
if [[ ! -d "$source_dir" ]]; then
    tar -xf "$archive" -C "$(dirname "$archive")"
fi
cd "$source_dir"
./configure --prefix="$prefix" --disable-debuginfod --disable-libdebuginfod \
    --disable-nls INSTALL=/usr/bin/install > "$root/logs/elfutils-configure.log" 2>&1
make -j"${JOBS:-$(nproc)}" > "$root/logs/elfutils-build.log" 2>&1
# Only install development libraries. This avoids unrelated debuginfod setup.
for component in libelf libdw libdwelf; do
    make -C "$component" INSTALL=/usr/bin/install install >> "$root/logs/elfutils-build.log" 2>&1
done
printf '%s\n' "$sha" > "$prefix/.sheng-host-tools-complete"

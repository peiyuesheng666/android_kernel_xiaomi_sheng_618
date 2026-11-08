#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Compile an ACK 6.18 development baseline in WSL. No sheng boot claim or flashing.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root=/root/sheng-618
source_dir="$root/src/ack"
output="$root/out/ack-arm64"
dist="$root/out/ack-dist"
sdk=/root/sheng-lineage/lineage-24.0/prebuilts
clang="$sdk/clang/host/linux-x86/clang-r584948b"
rust="$sdk/rust-toolchain/linux-x86/1.91.1"
clang_tools="$sdk/clang-tools/linux-x86"
build_tools="$sdk/kernel-build-tools/linux_musl-x86"
elfutils="$root/host-tools/elfutils-0.193"
bash "$project/scripts/prepare_kernel618_host_tools.sh"
[[ -f "$elfutils/include/elfutils/libdw.h" && -f "$elfutils/lib/libdw.so" ]]
expected_source=ff4a6c3bb0f471a9dd186293a47b62c83829b97d
[[ $(git -C "$source_dir" rev-parse HEAD) == "$expected_source" ]]
[[ -z $(git -C "$source_dir" status --porcelain) ]]
python3 "$project/scripts/kernel618_space.py" --root "$root" --output "$project/reports/kernel618-wsl-space.json"
python3 "$project/scripts/prepare_kernel618_sources.py" --preflight
export PATH="$clang/bin:$rust/bin:$clang_tools/bin:$build_tools/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LIBCLANG_PATH="$clang/lib"
export RUST_LIB_SRC="$rust/lib/rustlib/src/rust/library"
export RUSTC_BOOTSTRAP=1 KBUILD_GENDWARFKSYMS_STABLE=1
export LC_ALL=C LANG=C
export KBUILD_BUILD_USER=sheng KBUILD_BUILD_HOST=wsl KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP="$(git -C "$source_dir" show -s --format=%cD HEAD)"
export CCACHE_DIR=/root/sheng-lineage/ccache
export CCACHE_COMPRESS=true CCACHE_MAXSIZE=10G
jobs=${JOBS:-$(nproc)}
[[ "$jobs" =~ ^[1-9][0-9]*$ ]]
mkdir -p "$output" "$dist" "$root/logs"
log="$root/logs/build-ack.log"
status="$root/logs/build-status.txt"
trap 'rc=$?; if ((rc != 0)); then printf "failed exit=%s\n" "$rc" > "$status"; tail -n 70 "$log" >&2; fi' EXIT
args=(-C "$source_dir" O="$output" ARCH=arm64 LLVM=1 LLVM_IAS=1
    HOSTCFLAGS="-O2 -I$elfutils/include"
    HOSTLDFLAGS="-L$elfutils/lib -Wl,-rpath,$elfutils/lib"
    RUSTC="$rust/bin/rustc" HOSTRUSTC="$rust/bin/rustc"
    BINDGEN="$clang_tools/bin/bindgen" PAHOLE="$build_tools/bin/pahole"
    KCFLAGS=-D__ANDROID_COMMON_KERNEL__
    LOCALVERSION=-android17-5-sheng-ack-baseline)
if command -v ccache >/dev/null; then
    args+=(CC="ccache $clang/bin/clang")
fi
printf 'toolchain-check\n' > "$status"
{
    git -C "$source_dir" rev-parse HEAD
    clang --version
    rustc --version
    bindgen --version
    pahole --version
    make "${args[@]}" rustavailable
    make "${args[@]}" gki_defconfig
    "$source_dir/scripts/config" --file "$output/.config" --disable LOCALVERSION_AUTO
    # Use private elfutils 0.193 for current Clang DWARF5; distro 0.186
    # rejects the line tables even without compression. Keep all ABI checks.
    "$source_dir/scripts/config" --file "$output/.config" \
        --disable DEBUG_INFO_COMPRESSED_ZSTD --enable DEBUG_INFO_COMPRESSED_NONE
    make "${args[@]}" olddefconfig
    grep -qx 'CONFIG_RUST=y' "$output/.config"
    grep -qx 'CONFIG_MODVERSIONS=y' "$output/.config"
    grep -qx 'CONFIG_GENDWARFKSYMS=y' "$output/.config"
    grep -qx 'CONFIG_ANDROID_BINDER_IPC_RUST=m' "$output/.config"
} > "$log" 2>&1
printf 'compiling\n' > "$status"
printf 'Building ACK 6.18 Image and modules with %s jobs; log: %s\n' "$jobs" "$log"
make "${args[@]}" -j"$jobs" Image Image.gz modules >> "$log" 2>&1
printf 'installing-modules\n' > "$status"
make "${args[@]}" INSTALL_MOD_PATH="$dist/module-staging" INSTALL_MOD_STRIP=1 modules_install >> "$log" 2>&1
cp "$output/arch/arm64/boot/Image" "$output/arch/arm64/boot/Image.gz" "$output/System.map" "$output/Module.symvers" "$dist/"
cp "$output/.config" "$dist/ack.config"
cp "$output/include/config/kernel.release" "$dist/kernel.release"
git -C "$source_dir" rev-parse HEAD > "$dist/source.commit"
git -C "$source_dir" diff --exit-code >> "$log" 2>&1
printf 'complete\n' > "$status"
printf 'ACK baseline compiled: %s\n' "$(cat "$dist/kernel.release")"
printf 'This is not a sheng boot image. Output: %s\n' "$dist"

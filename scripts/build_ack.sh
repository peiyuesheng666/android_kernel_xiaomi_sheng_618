#!/usr/bin/env bash
# Build the unmodified official ACK with GKI config, not a sheng-ready image.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root=/root/sheng-612
source_dir="$root/src/common"
output="$root/out/ack-arm64"
dist="$root/out/ack-dist"
clang="$root/toolchains/clang-r536225"
rust="$root/toolchains/rust-1.82.0.p2"
build_tools="$root/toolchains/kernel-build-tools"
clang_tools="$root/toolchains/clang-tools"
export PATH="$clang/bin:$rust/bin:$clang_tools/bin:$build_tools/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LIBCLANG_PATH="$clang/lib"
export RUST_LIB_SRC="$rust/lib/rustlib/src/rust/library"
export RUSTC_BOOTSTRAP=1
export LC_ALL=C
export LANG=C
export KBUILD_BUILD_USER=sheng
export KBUILD_BUILD_HOST=wsl
export KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP="$(git -C "$source_dir" show -s --format=%cD HEAD)"
mkdir -p "$output" "$dist" "$root/logs" "$project/reports"
log="$root/logs/build-ack.log"
status="$root/logs/build-status.txt"
trap 'rc=$?; if ((rc != 0)); then printf "failed exit=%s\n" "$rc" > "$status"; tail -n 70 "$log" >&2; fi' EXIT
for exe in "$clang/bin/clang" "$rust/bin/rustc" "$clang_tools/bin/bindgen" "$build_tools/bin/pahole"; do
    [[ -x "$exe" ]] || { printf 'Missing required official tool: %s\n' "$exe" >&2; exit 1; }
done
[[ -f "$RUST_LIB_SRC/core/src/lib.rs" ]] || { echo 'Rust library sources missing' >&2; exit 1; }
args=(-C "$source_dir" O="$output" ARCH=arm64 LLVM=1 LLVM_IAS=1
    KCFLAGS=-D__ANDROID_COMMON_KERNEL__
    HOSTCFLAGS="-I$build_tools/include"
    HOSTLDFLAGS="-L$build_tools/lib64 -Wl,-rpath,$build_tools/lib64"
    LOCALVERSION=-android16-7-sheng-ack-baseline)
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
    make "${args[@]}" olddefconfig
    grep -qx 'CONFIG_RUST=y' "$output/.config"
    grep -qx 'CONFIG_MODVERSIONS=y' "$output/.config"
    grep -qx 'CONFIG_ANDROID_BINDER_IPC_RUST=m' "$output/.config"
} > "$log" 2>&1
printf 'compiling\n' > "$status"
echo "Building official ACK Image and modules in WSL; log: $log"
make "${args[@]}" -j"${JOBS:-12}" Image Image.gz modules >> "$log" 2>&1
printf 'packaging\n' > "$status"
make "${args[@]}" INSTALL_MOD_PATH="$dist/module-staging" INSTALL_MOD_STRIP=1 modules_install >> "$log" 2>&1
cp "$output/arch/arm64/boot/Image" "$output/arch/arm64/boot/Image.gz" "$output/System.map" "$output/Module.symvers" "$dist/"
cp "$output/.config" "$dist/ack.config"
cp "$output/include/config/kernel.release" "$dist/kernel.release"
git -C "$source_dir" rev-parse HEAD > "$dist/source.commit"
git -C "$source_dir" diff --exit-code >> "$log" 2>&1
python3 "$project/scripts/verify_build.py"
printf 'complete\n' > "$status"
echo "Complete: $(cat "$dist/kernel.release")"
echo "Artifacts: $dist"

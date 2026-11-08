#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root=/root/sheng-618
sdk=/root/sheng-lineage/lineage-24.0/prebuilts
clang="$sdk/clang/host/linux-x86/clang-r584948b"
rust="$sdk/rust-toolchain/linux-x86/1.91.1"
elfutils="$root/host-tools/elfutils-0.193"
export PATH="$clang/bin:$rust/bin:$sdk/clang-tools/linux-x86/bin:$sdk/kernel-build-tools/linux_musl-x86/bin:/usr/bin:/bin"
export LIBCLANG_PATH="$clang/lib" RUSTC_BOOTSTRAP=1 KBUILD_GENDWARFKSYMS_STABLE=1
export RUST_LIB_SRC="$rust/lib/rustlib/src/rust/library"
[[ $(cat "$root/logs/build-status.txt") == complete ]]
python3 "$project/scripts/prepare_kernel618_pogo_port.py"
make -C "$root/src/ack" O="$root/out/ack-arm64" M="$root/ports/pogo" \
    ARCH=arm64 LLVM=1 LLVM_IAS=1 -j"${JOBS:-$(nproc)}" \
    HOSTCFLAGS="-O2 -I$elfutils/include" HOSTLDFLAGS="-L$elfutils/lib -Wl,-rpath,$elfutils/lib" \
    RUSTC="$rust/bin/rustc" HOSTRUSTC="$rust/bin/rustc" \
    BINDGEN="$sdk/clang-tools/linux-x86/bin/bindgen" \
    PAHOLE="$sdk/kernel-build-tools/linux_musl-x86/bin/pahole" \
    KCFLAGS=-D__ANDROID_COMMON_KERNEL__ LOCALVERSION=-android17-5-sheng-ack-baseline \
    modules > "$root/logs/build-pogo-port.log" 2>&1
printf 'POGO utility module built (no device validation): %s\n' "$root/ports/pogo/xm_utils.ko"

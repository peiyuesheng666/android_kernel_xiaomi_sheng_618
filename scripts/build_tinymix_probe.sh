#!/usr/bin/env bash
# Build only a read-only mixer-listing diagnostic, using existing Android outputs.
set -euo pipefail
workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
rom=/root/sheng-lineage/lineage-24.0
cd "$rom"
output="$workspace/artifacts/audio-diagnostics-sheng"
mkdir -p "$output"
compiler=prebuilts/clang/host/linux-x86/clang-r596125/bin/clang
libroot=out/soong/.intermediates/bionic/libc
variant=android_vendor_arm64_armv8-2a-dotprod_kryo
"$compiler" --target=aarch64-linux-android35 -O2 -fPIE -pie -nostdlib -nostdinc \
    -D__ANDROID_VENDOR__ -DANDROID \
    -isystem bionic/libc/include -isystem bionic/libc/kernel/uapi \
    -isystem bionic/libc/kernel/android/uapi -isystem bionic/libc/kernel/uapi/asm-arm64 \
    -isystem prebuilts/clang/host/linux-x86/clang-r596125/lib/clang/22/include \
    -Iexternal/tinyalsa/include \
    "$libroot/crtbegin_dynamic/$variant/crtbegin_dynamic.o" \
    external/tinyalsa/tinymix.c \
    out/target/product/sheng/vendor/lib64/libtinyalsa.so \
    "$libroot/libc/${variant}_shared/libc.so" \
    "$libroot/crtend_android/$variant/crtend_android.o" \
    -Wl,--dynamic-linker,/system/bin/linker64 -Wl,-rpath,/vendor/lib64 \
    -o "$output/tinymix"
file "$output/tinymix"
sha256sum "$output/tinymix" > "$output/SHA256SUMS"

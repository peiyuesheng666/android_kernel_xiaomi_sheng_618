#!/usr/bin/env bash
set -euo pipefail
workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
probe_source=${1:-ShengAgmGainProbe.c}
probe_binary=${2:-sheng-agm-gain-probe}
rom=/root/sheng-lineage/lineage-24.0
cd "$rom"
compiler=prebuilts/clang/host/linux-x86/clang-r596125/bin/clang
libroot=out/soong/.intermediates/bionic/libc
variant=android_vendor_arm64_armv8-2a-dotprod_kryo
"$compiler" --target=aarch64-linux-android35 -O2 -fPIE -pie -nostdlib -nostdinc \
    -D__ANDROID_VENDOR__ -DANDROID \
    -isystem bionic/libc/include -isystem bionic/libc/kernel/uapi \
    -isystem bionic/libc/kernel/android/uapi -isystem bionic/libc/kernel/uapi/asm-arm64 \
    -isystem prebuilts/clang/host/linux-x86/clang-r596125/lib/clang/22/include \
    "$libroot/crtbegin_dynamic/$variant/crtbegin_dynamic.o" \
    "$workspace/scripts/$probe_source" \
    "$libroot/libc/${variant}_shared/libc.so" \
    "out/soong/.intermediates/bionic/libdl/libdl/${variant}_shared/libdl.so" \
    "$libroot/crtend_android/$variant/crtend_android.o" \
    -Wl,--dynamic-linker,/system/bin/linker64 -Wl,-rpath,/vendor/lib64 \
    -o "$workspace/artifacts/audio-diagnostics-sheng/$probe_binary"

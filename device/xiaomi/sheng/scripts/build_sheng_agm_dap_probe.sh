#!/usr/bin/env bash
# Build only the read-only device diagnostic, using the existing toolchain.
set -euo pipefail
device=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
workspace=$(cd "$device/../../.." && pwd)
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
    -I hardware/qcom-caf/sm8550/audio/graphservices/acdb/api \
    -I hardware/qcom-caf/sm8550/audio/graphservices/ar_osal/api \
    "$device/scripts/${SHENG_PROBE_SOURCE:-ShengAgmDapProbe.c}" \
    "$libroot/libc/${variant}_shared/libc.so" \
    "out/soong/.intermediates/bionic/libdl/libdl/${variant}_shared/libdl.so" \
    "$libroot/crtend_android/$variant/crtend_android.o" \
    -Wl,--dynamic-linker,/system/bin/linker64 -Wl,-rpath,/vendor/lib64 \
    -o "$workspace/artifacts/audio-diagnostics-sheng/${SHENG_PROBE_OUTPUT:-sheng-agm-dap-active-probe}"

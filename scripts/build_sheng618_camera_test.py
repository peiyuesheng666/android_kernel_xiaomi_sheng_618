#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build an ephemeral native camera test using read-only local Android headers."""
import subprocess
from build_sheng618_upstream import PROJECT, ROOT

rom = ROOT.parent/'sheng-lineage/lineage-24.0'
clang = rom/'prebuilts/clang/host/linux-x86/clang-r584948b/bin/clang'
sysroot = rom/'out/soong/ndk/sysroot'
libs = sysroot/'usr/lib/aarch64-linux-android/35'
crt = rom/'out/soong/.intermediates/bionic/libc'
begin = crt/'crtbegin_dynamic/android_arm64_armv8-2a-dotprod_kryo/crtbegin_dynamic.o'
end = crt/'crtend_android/android_arm64_armv8-2a-dotprod_kryo/crtend_android.o'
dest = ROOT/'diagnostic/camera-test'
dest.mkdir(parents=True, exist_ok=True)
args = [clang, '--target=aarch64-linux-android35', '--sysroot='+str(sysroot),
        '-isystem', sysroot/'usr/include/aarch64-linux-android', '-std=gnu11', '-O2',
        '-fPIE', '-pie', '-mno-outline-atomics', '-nostdlib', '-Wl,-dynamic-linker,/system/bin/linker64',
        begin, PROJECT/'scripts/sheng_camera_frames.c', '-L'+str(libs),
        '-lcamera2ndk', '-lmediandk', '-lnativewindow', '-landroid', '-lc', '-ldl', '-lm',
        end, '-o', dest/'sheng-camera-frames']
subprocess.run(list(map(str, args)), check=True)
print(dest/'sheng-camera-frames')
